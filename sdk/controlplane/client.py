import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx


class ControlPlane:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
    ):
        self.api_url = api_url.rstrip("/")

        self._executor = ThreadPoolExecutor(
            max_workers=4
        )

        # Shadow worker is created lazily.
        self._shadow_worker = None

    # =========================================================
    # TRACE / WORKFLOW
    # =========================================================

    def start_trace(
        self,
        name: str,
        session_id: str | None = None,
    ):
        # -----------------------------------------------------
        # PROJECT / SESSION ID
        #
        # If a developer runs a workflow interactively without
        # providing a project/session ID, ask for it in CMD.
        #
        # Non-interactive environments (CI, Docker, services)
        # must provide session_id explicitly so they never hang
        # waiting for input.
        # -----------------------------------------------------

        if not session_id or not session_id.strip():
            import sys

            if sys.stdin.isatty() and sys.stdout.isatty():
                print()
                print(
                    "ControlPlane: This workflow must belong "
                    "to a project."
                )
                print(
                    "Please enter a project/session ID."
                )

                session_id = input(
                    "Session ID: "
                ).strip()

                if not session_id:
                    raise ValueError(
                        "A session ID is required. "
                        "Every workflow must belong to a project."
                    )
            else:
                raise ValueError(
                    "session_id is required. "
                    "Every workflow must belong to a project. "
                    "Provide session_id when running in a "
                    "non-interactive environment."
                )

        from .trace import Trace

        trace = Trace(
            controlplane=self,
            name=name,
            session_id=session_id,
        )

        # -----------------------------------------------------
        # IMPORTANT
        #
        # Create the workflow synchronously.
        #
        # This guarantees that Trace.__enter__() can safely
        # PATCH the workflow to "running".
        # -----------------------------------------------------

        self._create_workflow_trace(
            trace_id=trace.id,
            name=name,
            session_id=session_id,
        )

        return trace

    def _create_workflow_trace(
        self,
        *,
        trace_id: str,
        name: str,
        session_id: str,
    ):
        payload = {
            "id": trace_id,
            "provider": "controlplane",
            "model": "workflow",

            "input": name,
            "output": None,

            "input_tokens": None,
            "output_tokens": None,

            "latency_ms": None,

            "estimated_cost_usd": None,

            "context": None,

            "session_id": session_id,

            "status": "pending",

            "safety_flag": False,
            "safety_type": None,
            "safety_action": None,

            "parent_trace_id": None,

            "started_at": None,
            "ended_at": None,
        }

        # -----------------------------------------------------
        # DO NOT QUEUE THIS.
        #
        # The workflow record must exist before lifecycle
        # updates are sent.
        # -----------------------------------------------------

        self._send_workflow_trace(payload)

    def _send_workflow_trace(
        self,
        payload: dict,
    ):
        try:
            response = httpx.post(
                f"{self.api_url}/traces",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

            print(
                "WORKFLOW TRACE STORED:",
                payload["id"],
            )

        except Exception as error:
            print(
                f"ControlPlane workflow trace failed: {error}"
            )

            # -------------------------------------------------
            # IMPORTANT
            #
            # Workflow telemetry is required for lifecycle
            # correctness. If creation fails, do not silently
            # pretend that the workflow was registered.
            # -------------------------------------------------

            raise

    # =========================================================
    # UPDATE WORKFLOW LIFECYCLE
    # =========================================================

    def update_trace(
        self,
        *,
        trace_id: str,
        started_at: str | None = None,
        ended_at: str | None = None,
        latency_ms: int | None = None,
        status: str | None = None,
    ):
        payload = {
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_ms": latency_ms,
            "status": status,
        }

        self._executor.submit(
            self._send_trace_update,
            trace_id,
            payload,
        )

    def _send_trace_update(
        self,
        trace_id: str,
        payload: dict,
    ):
        try:
            response = httpx.patch(
                f"{self.api_url}/traces/{trace_id}",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

            print(
                "TRACE UPDATED:",
                trace_id,
                payload,
            )

        except Exception as error:
            print(
                f"ControlPlane trace update failed: {error}"
            )

    # =========================================================
    # LLM TRACE
    # =========================================================

    def trace(
        self,
        *,
        provider: str,
        model: str,
        input: str,
        output: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        estimated_cost_usd: float | None = None,
        context: str | None = None,
        session_id: str,
        status: str = "success",
        safety_flag: bool = False,
        safety_type: str | None = None,
        safety_action: str | None = None,
        parent_trace_id: str | None = None,
    ):
        if not session_id or not session_id.strip():
            raise ValueError(
                "session_id is required. "
                "Every trace must belong to a project."
            )

        trace_id = str(uuid.uuid4())

        payload = {
            "id": trace_id,

            "provider": provider,
            "model": model,

            "input": input,
            "output": output,

            "input_tokens": input_tokens,
            "output_tokens": output_tokens,

            "latency_ms": latency_ms,

            "estimated_cost_usd": estimated_cost_usd,

            "context": context,

            "session_id": session_id,

            "status": status,

            "safety_flag": safety_flag,
            "safety_type": safety_type,
            "safety_action": safety_action,

            "parent_trace_id": parent_trace_id,
        }

        # LLM telemetry remains asynchronous.
        self._executor.submit(
            self._send_trace_and_evaluate,
            payload,
        )

        return trace_id

    def _send_trace_and_evaluate(
        self,
        payload: dict,
    ):
        try:
            # -------------------------------------------------
            # STORE LLM TRACE
            # -------------------------------------------------

            response = httpx.post(
                f"{self.api_url}/traces",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

            print(
                "LLM TRACE STORED:",
                payload["id"],
            )

            # -------------------------------------------------
            # SHADOW EVALUATION
            # -------------------------------------------------

            if (
                payload["status"] == "success"
                and payload["context"]
                and payload["output"]
            ):
                if self._shadow_worker is None:
                    from .shadow.worker import ShadowWorker

                    self._shadow_worker = ShadowWorker()

                self._shadow_worker.evaluate_trace(
                    payload["id"]
                )

        except Exception as error:
            print(
                f"ControlPlane trace failed: {error}"
            )

    # =========================================================
    # SPANS
    # =========================================================

    def record_span(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        name: str,
        span_type: str,
        input: str | None = None,
        output: str | None = None,
        duration_ms: int | None = None,
        status: str = "success",
        metadata: dict | None = None,
    ):
        payload = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,

            "name": name,
            "span_type": span_type,

            "input": input,
            "output": output,

            "duration_ms": duration_ms,

            "status": status,

            "metadata": metadata or {},
        }

        # Spans remain asynchronous so telemetry doesn't
        # unnecessarily block the application.
        self._executor.submit(
            self._send_span,
            payload,
        )

    def _send_span(
        self,
        payload: dict,
    ):
        try:
            response = httpx.post(
                f"{self.api_url}/spans",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

            print(
                "SPAN STORED:",
                payload["name"],
                payload["span_id"],
                "trace:",
                payload["trace_id"],
            )

        except Exception as error:
            print(
                f"ControlPlane span failed: {error}"
            )

    # =========================================================
    # FLUSH
    # =========================================================

    def flush(self):
        """
        Wait for all queued telemetry requests to finish.

        The executor is recreated afterward so the
        ControlPlane instance can continue to be used.
        """

        print(
            "FLUSHING CONTROLPLANE TELEMETRY..."
        )

        self._executor.shutdown(
            wait=True
        )

        self._executor = ThreadPoolExecutor(
            max_workers=4
        )

        print(
            "CONTROLPLANE TELEMETRY FLUSHED."
        )

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self):
        """
        Permanently shut down telemetry workers.
        """

        print(
            "SHUTTING DOWN CONTROLPLANE..."
        )

        self._executor.shutdown(
            wait=True
        )

        print(
            "CONTROLPLANE SHUT DOWN."
        )