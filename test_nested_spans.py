import time

from controlplane import ControlPlane


cp = ControlPlane()


with cp.start_trace(
    "customer-request",
    session_id="nested-test-001",
) as trace:

    with trace.span(
        "agent",
        span_type="agent",
    ) as agent:

        with agent.span(
            "retrieval",
            span_type="retrieval",
        ):
            time.sleep(0.2)

        with agent.span(
            "openai",
            span_type="llm",
        ):
            time.sleep(0.5)

        with agent.span(
            "database",
            span_type="database",
        ):
            time.sleep(0.1)


print("Trace:", trace.id)
print("Nested span test complete.")