import time

from dotenv import load_dotenv

from controlplane import ControlPlane, OpenAIClient


load_dotenv()


cp = ControlPlane()


openai = OpenAIClient(
    controlplane=cp,
)


start = time.perf_counter()


response = openai.chat(
    model="gpt-4.1-mini",
    messages=[
        {
            "role": "user",
            "content": (
                "What is our refund policy?"
            ),
        }
    ],
    context=(
        "Customers can request a refund within "
        "30 days of purchase."
    ),
    session_id="shadow-test-001",
)


end = time.perf_counter()


elapsed_ms = (end - start) * 1000


print("Response:")
print(response.choices[0].message.content)

print(f"Total application time: {elapsed_ms:.2f} ms")