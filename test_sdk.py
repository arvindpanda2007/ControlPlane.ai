from controlplane import ControlPlane


cp = ControlPlane()

result = cp.trace(
    provider="openai",
    model="gpt-4.1-mini",
    input="What is our refund policy?",
    output="Customers can request a refund within 30 days.",
    input_tokens=42,
    output_tokens=18,
    latency_ms=684,
    session_id="demo-session-001",
)

print(result)