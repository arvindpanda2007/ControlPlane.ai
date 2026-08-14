import json

from openai import OpenAI


class ShadowEvaluator:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4.1-mini",
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def evaluate_factuality(
        self,
        *,
        context: str,
        output: str,
    ) -> dict:

        if not context:
            return {
                "score": None,
                "status": "not_applicable",
                "reason": "No context was provided.",
            }

        if not output:
            return {
                "score": 0.0,
                "status": "unsupported",
                "reason": "No model output was provided.",
            }

        prompt = f"""
You are evaluating whether an AI response is grounded
in the supplied context.

Use ONLY the supplied context.
Do not use outside knowledge.

CONTEXT:
{context}

RESPONSE:
{output}

Evaluate how well the RESPONSE is supported by the CONTEXT.

Return ONLY valid JSON:

{{
    "score": 0.0,
    "reason": "short explanation"
}}

Rules:

- score must be between 0.0 and 1.0
- 1.0 means fully supported
- 0.0 means completely unsupported
- partial support should receive a value between them
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a factuality evaluator. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
        )

        text = response.choices[0].message.content or "{}"

        result = json.loads(text)

        score = float(result["score"])
        score = max(0.0, min(1.0, score))

        if score >= 0.80:
            status = "supported"
        elif score >= 0.40:
            status = "partially_supported"
        else:
            status = "unsupported"

        return {
            "score": score,
            "status": status,
            "reason": result.get("reason", ""),
        }