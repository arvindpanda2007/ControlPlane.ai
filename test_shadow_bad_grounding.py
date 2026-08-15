import json
import httpx
from dotenv import load_dotenv

load_dotenv()

from controlplane.shadow.evaluator import ShadowEvaluator


USER_INPUT = "What is artificial intelligence?"

CONTEXT = """
Artificial intelligence is the simulation of human intelligence by machines.
It includes learning, reasoning, problem-solving, language understanding,
and perception.
"""

# Deliberately includes claims that are NOT established by the supplied context.
OUTPUT = """
Artificial intelligence is the simulation of human intelligence by machines.
It includes learning, reasoning, problem-solving, language understanding,
and perception.

AI systems range from simple rule-based systems to complex neural networks.
AI is widely used in autonomous vehicles, recommendation systems, and
virtual assistants.
AI can also improve its performance over time through experience.
"""


def main():
    evaluator = ShadowEvaluator()

    result = evaluator.evaluate(
        user_input=USER_INPUT,
        context=CONTEXT,
        output=OUTPUT,
        spans=[
            {
                "id": "test-agent-span",
                "parent_span_id": None,
                "name": "agent",
                "span_type": "agent",
                "input": USER_INPUT,
                "output": OUTPUT,
                "duration_ms": 100,
                "status": "success",
                "metadata": {},
            },
            {
                "id": "test-openai-span",
                "parent_span_id": "test-agent-span",
                "name": "openai",
                "span_type": "llm",
                "input": USER_INPUT,
                "output": OUTPUT,
                "duration_ms": 90,
                "status": "success",
                "metadata": {},
            },
        ],
    )

    print("\n=== SHADOW RESULT ===")
    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    recommendations = result.get("recommendations", [])

    print("\n=== RECOMMENDATION COUNT ===")
    print(len(recommendations))

    print("\n=== RECOMMENDATIONS ===")

    for index, recommendation in enumerate(
        recommendations,
        start=1,
    ):
        print(f"\n[{index}]")
        print(
            json.dumps(
                recommendation,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )

    # ---------------------------------------------------------
    # ASSERTIONS
    # ---------------------------------------------------------

    assert recommendations, (
        "Expected Shadow to produce at least one "
        "recommendation for unsupported claims."
    )

    # We specifically want consolidation.
    titles = [
        str(item.get("title") or "").lower()
        for item in recommendations
    ]

    grounding_recommendations = [
        item
        for item in recommendations
        if any(
            keyword in (
                str(item.get("category") or "")
                + " "
                + str(item.get("title") or "")
                + " "
                + str(item.get("problem") or "")
            ).lower()
            for keyword in (
                "ground",
                "unsupported",
                "hallucination",
                "context",
            )
        )
    ]

    assert grounding_recommendations, (
        "Expected a grounding/context/hallucination "
        "recommendation."
    )

    # Make sure evidence exists.
    for recommendation in grounding_recommendations:
        evidence = recommendation.get(
            "evidence",
            [],
        )

        assert isinstance(evidence, list), (
            "Recommendation evidence must be a list."
        )

        assert evidence, (
            "Grounding recommendation must contain evidence."
        )

    print("\n========================================")
    print("BAD-GROUNDING TEST PASSED")
    print("========================================")
    print(
        f"Recommendations: {len(recommendations)}"
    )


if __name__ == "__main__":
    main()