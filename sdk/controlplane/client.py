import uuid

import httpx
from concurrent.futures import ThreadPoolExecutor


class ControlPlane:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
    ):
        self.api_url = api_url.rstrip("/")
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Shadow worker is created lazily.
        self._shadow_worker = None

    # ---------------------------------------------------------
    # TRACE / WORKFLOW
    # ---------------------------------------------------------

    def start_trace(
        self,
        name: str,
        session_id: str | None = None,
    ):
        from .trace import Trace

        return Trace(
            controlplane=self,
            name=name,
            session_id=session_id,
        )

    # ---------------------------------------------------------
    # LLM TRACE
    # ---------------------------------------------------------

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
        session_id: str | None = None,
        status: str = "success",
        safety_flag: bool = False,
        safety_type: str | None = None,
        safety_action: str | None = None,
    ):
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
        }

        self._executor.submit(
            self._send_trace_and_evaluate,
            payload,
        )

    def _send_trace_and_evaluate(self, payload: dict):
        try:
            # -------------------------------------------------
            # 1. Store trace
            # -------------------------------------------------

            response = httpx.post(
                f"{self.api_url}/traces",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

            # -------------------------------------------------
            # 2. Shadow evaluation
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

    # ---------------------------------------------------------
    # SPANS
    # ---------------------------------------------------------

    def record_span(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        name: str,
        span_type: str,
        duration_ms: int,
        status: str,
        metadata: dict | None = None,
    ):
        payload = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "span_type": span_type,
            "duration_ms": duration_ms,
            "status": status,
            "metadata": metadata or {},
        }

        self._executor.submit(
            self._send_span,
            payload,
        )

    def _send_span(self, payload: dict):
        try:
            response = httpx.post(
                f"{self.api_url}/spans",
                json=payload,
                timeout=5.0,
            )

            response.raise_for_status()

        except Exception as error:
            print(
                f"ControlPlane span failed: {error}"
            )