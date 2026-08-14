import time

from controlplane import ControlPlane


cp = ControlPlane()


with cp.start_trace(
    "customer-refund",
    session_id="span-test-001",
) as trace:

    with trace.span(
        "retrieval",
        span_type="retrieval",
    ):
        time.sleep(0.2)

    with trace.span(
        "openai",
        span_type="llm",
    ):
        time.sleep(0.5)

    with trace.span(
        "database",
        span_type="database",
    ):
        time.sleep(0.1)


print("Trace:", trace.id)
print("Span test complete.")