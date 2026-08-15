from controlplane.client import ControlPlane
from controlplane.openai import OpenAIClient
from dotenv import load_dotenv

load_dotenv()

controlplane = ControlPlane()

openai = OpenAIClient(
    controlplane=controlplane,
)


with controlplane.start_trace(
    name="openai-shadow-test",
    session_id="openai-shadow-test-001",
) as trace:

    with trace.span(
        "agent",
        span_type="agent",
    ):

        response = openai.chat(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": "What is artificial intelligence?",
                }
            ],
            context=(
                "Artificial intelligence is the simulation "
                "of human intelligence by machines. "
                "It includes learning, reasoning, "
                "problem-solving, language understanding, "
                "and perception."
            ),
            session_id="openai-shadow-test-001",
            trace=trace,
        )

        print("Response:")
        print(response.choices[0].message.content)

        print()
        print("Trace:", trace.id)

print()
print("OpenAI trace test complete.")