import time
import uuid


class Span:
    def __init__(
        self,
        trace: "Trace",
        name: str,
        span_type: str = "custom",
        parent_span_id: str | None = None,
        metadata: dict | None = None,
    ):
        self.trace = trace
        self.name = name
        self.span_type = span_type
        self.parent_span_id = parent_span_id
        self.metadata = metadata or {}

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
    ):
        return Span(
            trace=self.trace,
            name=name,
            span_type=span_type,
            parent_span_id=self.id,
            metadata=metadata,
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

        self.duration_ms = int(
            (self.ended_at - self.started_at) * 1000
        )

        status = (
            "error"
            if exc_type
            else "success"
        )

        # Record the completed span asynchronously.
        self.trace.controlplane.record_span(
            trace_id=self.trace.id,
            span_id=self.id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            span_type=self.span_type,
            duration_ms=self.duration_ms,
            status=status,
            metadata=self.metadata,
        )

        # False means any exception should continue
        # propagating to the caller.
        return False


class Trace:
    def __init__(
        self,
        controlplane,
        name: str,
        session_id: str | None = None,
    ):
        self.controlplane = controlplane

        # This is the SINGLE canonical ID for the
        # entire workflow.
        self.id = str(uuid.uuid4())

        self.name = name
        self.session_id = session_id

    # ---------------------------------------------------------
    # START TRACE
    # ---------------------------------------------------------

    def __enter__(self):
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
        return False

    # ---------------------------------------------------------
    # CREATE ROOT SPAN
    # ---------------------------------------------------------

    def span(
        self,
        name: str,
        span_type: str = "custom",
        metadata: dict | None = None,
    ):
        return Span(
            trace=self,
            name=name,
            span_type=span_type,
            metadata=metadata,
        )