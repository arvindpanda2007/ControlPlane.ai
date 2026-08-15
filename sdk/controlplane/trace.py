import time
import uuid
from datetime import datetime, timezone


class Span:
    def __init__(
        self,
        trace: "Trace",
        name: str,
        span_type: str = "custom",
        parent_span_id: str | None = None,
        metadata: dict | None = None,
        input: str | None = None,
        output: str | None = None,
    ):
        self.trace = trace
        self.name = name
        self.span_type = span_type
        self.parent_span_id = parent_span_id
        self.metadata = metadata or {}

        # -----------------------------------------------------
        # STEP INPUT / OUTPUT
        # -----------------------------------------------------

        self.input = input
        self.output = output

        # -----------------------------------------------------
        # SPAN ID / TIMING
        # -----------------------------------------------------

        self.id = str(uuid.uuid4())

        self.started_at = None
        self.ended_at = None
        self.duration_ms = None

    # ---------------------------------------------------------
    # NESTED SPANS
    # ---------------------------------------------------------

    def span(
        self,
        name: str,
        span_type: str = "custom",
        metadata: dict | None = None,
        input: str | None = None,
        output: str | None = None,
    ):
        return Span(
            trace=self.trace,
            name=name,
            span_type=span_type,
            parent_span_id=self.id,
            metadata=metadata,
            input=input,
            output=output,
        )

    # ---------------------------------------------------------
    # START SPAN
    # ---------------------------------------------------------

    def __enter__(self):
        self.started_at = time.perf_counter()

        return self

    # ---------------------------------------------------------
    # FINISH SPAN
    # ---------------------------------------------------------

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.ended_at = time.perf_counter()

        if self.started_at is not None:
            self.duration_ms = int(
                (self.ended_at - self.started_at) * 1000
            )
        else:
            self.duration_ms = 0

        status = (
            "error"
            if exc_type
            else "success"
        )

        # -----------------------------------------------------
        # ERROR INFORMATION
        # -----------------------------------------------------

        if exc_type:
            self.metadata.update(
                {
                    "error": True,
                    "error_type": exc_type.__name__,
                }
            )

        # -----------------------------------------------------
        # RECORD SPAN
        # -----------------------------------------------------

        try:
            self.trace.controlplane.record_span(
                trace_id=self.trace.id,
                span_id=self.id,
                parent_span_id=self.parent_span_id,
                name=self.name,
                span_type=self.span_type,
                input=self.input,
                output=self.output,
                duration_ms=self.duration_ms,
                status=status,
                metadata=self.metadata,
            )

        except Exception as error:
            # Telemetry must never break the application.
            print(
                f"ControlPlane span recording failed: {error}"
            )

        # Never swallow application exceptions.
        return False


class Trace:
    def __init__(
        self,
        controlplane,
        name: str,
        session_id: str | None = None,
    ):
        self.controlplane = controlplane

        # -----------------------------------------------------
        # CANONICAL WORKFLOW ID
        # -----------------------------------------------------

        self.id = str(uuid.uuid4())

        self.name = name
        self.session_id = session_id

        # -----------------------------------------------------
        # WORKFLOW LIFECYCLE
        # -----------------------------------------------------

        self.started_at = None
        self.ended_at = None

        self._started_perf = None
        self.latency_ms = None

        self.status = "pending"

    # ---------------------------------------------------------
    # START TRACE
    # ---------------------------------------------------------

    def __enter__(self):
        self.started_at = datetime.now(
            timezone.utc
        )

        self._started_perf = time.perf_counter()

        self.status = "running"

        # Tell the backend that execution has started.
        self.controlplane.update_trace(
            trace_id=self.id,
            started_at=self.started_at.isoformat(),
            status="running",
        )

        return self

    # ---------------------------------------------------------
    # FINISH TRACE
    # ---------------------------------------------------------

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.ended_at = datetime.now(
            timezone.utc
        )

        if self._started_perf is not None:
            self.latency_ms = int(
                (time.perf_counter() - self._started_perf)
                * 1000
            )
        else:
            self.latency_ms = 0

        # -----------------------------------------------------
        # FINAL STATUS
        # -----------------------------------------------------

        if exc_type is None:
            self.status = "success"
        else:
            self.status = "error"

        # -----------------------------------------------------
        # UPDATE BACKEND
        # -----------------------------------------------------

        try:
            self.controlplane.update_trace(
                trace_id=self.id,
                started_at=self.started_at.isoformat()
                if self.started_at
                else None,
                ended_at=self.ended_at.isoformat(),
                latency_ms=self.latency_ms,
                status=self.status,
            )

        except Exception as error:
            print(
                f"ControlPlane trace update failed: {error}"
            )

        # Never swallow application exceptions.
        return False

    # ---------------------------------------------------------
    # CREATE ROOT SPAN
    # ---------------------------------------------------------

    def span(
        self,
        name: str,
        span_type: str = "custom",
        metadata: dict | None = None,
        input: str | None = None,
        output: str | None = None,
    ):
        return Span(
            trace=self,
            name=name,
            span_type=span_type,
            metadata=metadata,
            input=input,
            output=output,
        )