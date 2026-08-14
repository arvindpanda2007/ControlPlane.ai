import time

from dotenv import load_dotenv

from controlplane import ControlPlane, OpenAIClient


load_dotenv()

cp = ControlPlane()

openai = OpenAIClient(
    controlplane=cp,
)


with cp.start_trace(
    "customer-refund",
    session_id="openai-span-test-001",
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

        response = openai.chat(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": "What is artificial intelligence?",
                }
            ],
            session_id="openai-span-test-001",
            trace=agent,
        )


print("Response:")
print(response.choices[0].message.content)

print("Trace:", trace.id)
print("OpenAI trace test complete.")