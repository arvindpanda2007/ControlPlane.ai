from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import httpx
import json
import uuid


def _serialize_context(value):
    if value is None or isinstance(value, str):
        return value

    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


class Span:
    """Opaque developer-facing span handle.

    Developers may pass a Span returned by run.span(...) as the parent of
    another span, but they never provide or generate its ID.
    """

    def __init__(self, run: "Run", span_id: str, name: str):
        self._run = run
        self._id = str(span_id)
        self.name = name

    @property
    def id(self):
        # Intentionally private to normal application code.
        return self._id

    def __repr__(self):
        return f"Span(name={self.name!r})"


class Run:
    """
    Public application-run handle.

    Developer contract:

        app = cp.application("Weather Agent", session_id="messi")

        with app.run(input="...", context={...}) as run:
            root = run.span(...)
            child = run.span(..., parent=root)

    The developer never supplies application IDs, run IDs, trace IDs,
    span IDs, or parent ID strings. ControlPlane owns all identifiers.
    """

    def __init__(
        self,
        controlplane: "ControlPlane",
        application_id: str,
        run_id: str,
        application_name: str,
        session_id: str,
        input: Any = None,
        context: Any = None,
    ):
        self._controlplane = controlplane
        self._application_id = str(application_id)
        self._run_id = str(run_id)
        self._application_name = application_name
        self._session_id = session_id
        self._input = input
        self._context = context

        self._trace_id: str | None = None
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._closed = False

    @property
    def id(self):
        """Server-created run identifier."""
        return self._run_id

    @property
    def application_id(self):
        """Server-created application identifier."""
        return self._application_id

    def __enter__(self):
        self._started_at = datetime.now(timezone.utc).isoformat()

        data = self._controlplane._create_run_trace(
            run_id=self._run_id,
            application_name=self._application_name,
            session_id=self._session_id,
            input=self._input,
            context=self._context,
        )

        trace_id = data.get("trace_id") or data.get("id")

        if not trace_id:
            raise RuntimeError(
                "ControlPlane did not return the internal run trace ID."
            )

        self._trace_id = str(trace_id)

        self._controlplane._update_run(
            self._run_id,
            started_at=self._started_at,
            status="running",
        )

        return self

    def __exit__(self, exc_type, exc, tb):
        self._ended_at = datetime.now(timezone.utc).isoformat()

        status = "error" if exc is not None else "success"

        if self._trace_id:
            started = self._started_at
            latency_ms = None

            if started:
                try:
                    start_dt = datetime.fromisoformat(started)
                    end_dt = datetime.fromisoformat(self._ended_at)

                    latency_ms = max(
                        0,
                        int(
                            (end_dt - start_dt).total_seconds() * 1000
                        ),
                    )
                except Exception:
                    latency_ms = None

            self._controlplane._update_run(
                self._run_id,
                ended_at=self._ended_at,
                latency_ms=latency_ms,
                status=status,
            )

        self._closed = True
        return False

    def span(
        self,
        name: str,
        span_type: str,
        input_data: Any = None,
        output_data: Any = None,
        *,
        parent: Span | None = None,
        duration_ms: int | None = None,
        status: str = "success",
        metadata: dict | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> Span:
        """
        Record a span inside this run.

        `parent` accepts a Span handle, never a parent span ID.
        ControlPlane generates the actual span ID.
        """

        if self._trace_id is None:
            raise RuntimeError(
                "Run must be entered with 'with app.run(...) as run:' "
                "before recording spans."
            )

        parent_id = parent._id if parent is not None else None

        data = self._controlplane._create_span(
            trace_id=self._trace_id,
            parent_span_id=parent_id,
            name=name,
            span_type=span_type,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration_ms,
            status=status,
            metadata=metadata,
            started_at=started_at,
            ended_at=ended_at,
        )

        span_id = data.get("span_id") or data.get("id")

        if not span_id:
            raise RuntimeError(
                f"ControlPlane did not return a span ID for {name!r}."
            )

        return Span(self, span_id, name)

    def error_span(
        self,
        name: str,
        span_type: str,
        input_data: Any,
        exc: Exception,
        *,
        parent: Span | None = None,
        metadata: dict | None = None,
    ) -> Span:
        merged = {
            **(metadata or {}),
            "error_type": type(exc).__name__,
        }

        return self.span(
            name=name,
            span_type=span_type,
            input_data=input_data,
            output_data={"error": str(exc)},
            parent=parent,
            duration_ms=0,
            status="error",
            metadata=merged,
        )

    # ---------------------------------------------------------
    # Internal/test-only readback.
    # ---------------------------------------------------------

    def _get_spans(self):
        if self._trace_id is None:
            raise RuntimeError("Run has not started.")

        response = self._controlplane._get(
            f"/traces/{self._trace_id}/spans"
        )

        return response


class Application:
    """
    Public ControlPlane application.

    The developer names the application once. ControlPlane owns every
    application, run, trace, and span identifier.
    """

    def __init__(
        self,
        controlplane: "ControlPlane",
        name: str,
        session_id: str | None = None,
    ):
        name = name.strip()

        if not name:
            raise ValueError("Application name is required.")

        self._controlplane = controlplane
        self.name = name
        self.session_id = session_id.strip() if session_id else None
        self._application_id: str | None = None

    def run(
        self,
        *,
        input: Any = None,
        context: Any = None,
    ) -> Run:
        session_id = self.session_id

        if not session_id:
            import sys

            if sys.stdin.isatty() and sys.stdout.isatty():
                print()
                print("ControlPlane application setup")
                print("-" * 70)

                session_id = input("Project/session ID: ").strip()

                if not session_id:
                    raise ValueError(
                        "A project/session ID is required."
                    )

                self.session_id = session_id

            else:
                raise ValueError(
                    "session_id is required. Provide session_id when "
                    "running in a non-interactive environment."
                )

        if self._application_id is None:
            self._application_id = self._controlplane._create_application(
                name=self.name,
                session_id=session_id,
            )

        run_id = self._controlplane._create_run(
            application_id=self._application_id,
            input=input,
            context=context,
        )

        return Run(
            controlplane=self._controlplane,
            application_id=self._application_id,
            run_id=run_id,
            application_name=self.name,
            session_id=session_id,
            input=input,
            context=context,
        )

    def __repr__(self):
        return f"Application(name={self.name!r})"


class ControlPlane:
    """
    Public SDK entry point.

    Intentional public surface:

        cp.application("My Application", session_id="project")

    Low-level ID-based telemetry methods are private so application
    developers cannot choose trace/span identifiers.
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
    ):
        self.api_url = api_url.rstrip("/")
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._shadow_worker = None

    def application(
        self,
        name: str,
        session_id: str | None = None,
    ) -> Application:
        return Application(
            controlplane=self,
            name=name,
            session_id=session_id,
        )

    # =========================================================
    # INTERNAL APPLICATION / RUN API
    # =========================================================

    def _post(self, path: str, payload: dict):
        response = httpx.post(
            f"{self.api_url}{path}",
            json=payload,
            timeout=5.0,
        )

        response.raise_for_status()

        return response.json() if response.content else {}

    def _get(self, path: str):
        response = httpx.get(
            f"{self.api_url}{path}",
            timeout=5.0,
        )

        response.raise_for_status()

        return response.json()

    def _patch(self, path: str, payload: dict):
        response = httpx.patch(
            f"{self.api_url}{path}",
            json=payload,
            timeout=5.0,
        )

        response.raise_for_status()

        return response.json() if response.content else {}

    def _create_application(
        self,
        *,
        name: str,
        session_id: str,
    ) -> str:
        data = self._post(
            "/applications",
            {
                "name": name,
                "session_id": session_id,
            },
        )

        application_id = (
            data.get("application_id")
            or data.get("id")
        )

        if not application_id:
            raise RuntimeError(
                "ControlPlane did not return an application ID."
            )

        return str(application_id)

    def _create_run(
        self,
        *,
        application_id: str,
        input: Any = None,
        context: Any = None,
    ) -> str:
        data = self._post(
            f"/applications/{application_id}/runs",
            {
                "input": (
                    input
                    if input is None or isinstance(input, str)
                    else str(input)
                ),
                "context": _serialize_context(context),
            },
        )

        run_id = data.get("run_id") or data.get("id")

        if not run_id:
            raise RuntimeError(
                "ControlPlane did not return a run ID."
            )

        return str(run_id)

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
        parent_trace_id: str | None = None,
    ):
        """
        Record an LLM trace and asynchronously run Shadow evaluation.

        The trace is persisted synchronously so token usage, cost, output,
        and the trace ID are available to the backend immediately.
        Shadow runs only after the trace has been successfully stored.
        """

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

        # Persist the LLM trace before dispatching Shadow.
        self._send_llm_trace(payload)

        # Shadow must run after the trace exists in the database.
        if (
            status == "success"
            and context
            and output
        ):
            self._executor.submit(
                self._run_shadow_evaluation,
                trace_id,
            )

        return trace_id

    def _send_llm_trace(
        self,
        payload: dict,
    ):
        """Persist an LLM trace immediately."""
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

    def _run_shadow_evaluation(
        self,
        trace_id: str,
    ):
        """Run Shadow asynchronously after the trace is persisted."""
        try:
            if self._shadow_worker is None:
                from .shadow.worker import ShadowWorker

                self._shadow_worker = ShadowWorker()

            self._shadow_worker.evaluate_trace(
                trace_id
            )

            print(
                "SHADOW EVALUATION COMPLETE:",
                trace_id,
            )

        except Exception as error:
            print(
                f"ControlPlane shadow evaluation failed: {error}"
            )

    def _create_trace(
        self,
        *,
        run_id: str,
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
        parent_trace_id: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ):
        """
        Create a child trace.

        The server generates the trace ID. Application developers never
        provide one.
        """

        return self._post(
            f"/runs/{run_id}/traces",
            {
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
                "started_at": started_at,
                "ended_at": ended_at,
            },
        )

    def _create_run_trace(
        self,
        *,
        run_id: str,
        application_name: str,
        session_id: str,
        input: Any,
        context: Any,
    ):
        # No trace ID is supplied. The API creates it.
        return self._post(
            f"/runs/{run_id}/traces",
            {
                "provider": "controlplane",
                "model": "workflow",
                "input": (
                    str(input)
                    if input is not None
                    else application_name
                ),
                "output": None,
                "context": _serialize_context(context),
                "session_id": session_id,
                "status": "pending",
            },
        )

    def _update_run(
        self,
        run_id: str,
        *,
        started_at: str | None = None,
        ended_at: str | None = None,
        latency_ms: int | None = None,
        status: str | None = None,
    ):
        self._patch(
            f"/runs/{run_id}",
            {
                "started_at": started_at,
                "ended_at": ended_at,
                "latency_ms": latency_ms,
                "status": status,
            },
        )

    def _create_span(
        self,
        *,
        trace_id: str,
        parent_span_id: str | None,
        name: str,
        span_type: str,
        input_data: Any,
        output_data: Any,
        duration_ms: int | None,
        status: str,
        metadata: dict | None,
        started_at: str | None,
        ended_at: str | None,
    ):
        payload = {
            "parent_span_id": parent_span_id,
            "name": name,
            "span_type": span_type,
            "input": input_data,
            "output": output_data,
            "duration_ms": duration_ms,
            "status": status,
            "metadata": metadata or {},
        }

        if started_at is not None:
            payload["started_at"] = started_at

        if ended_at is not None:
            payload["ended_at"] = ended_at

        # No span ID is supplied. The API creates it.
        return self._post(
            f"/traces/{trace_id}/spans",
            payload,
        )

    def flush(self):
        # Public only for application shutdown/testing; IDs remain private.
        self._executor.shutdown(wait=True)
        self._executor = ThreadPoolExecutor(max_workers=4)

    def shutdown(self):
        self._executor.shutdown(wait=True)