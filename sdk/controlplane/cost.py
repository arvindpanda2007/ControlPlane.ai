MODEL_PRICING = {
    "gpt-4.1-mini": {
        "input_per_1m": 0.40,
        "output_per_1m": 1.60,
    },
}


def calculate_cost(
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """
    Calculate estimated model cost in USD.

    Returns None when token usage or model pricing
    is unavailable.
    """

    if input_tokens is None or output_tokens is None:
        return None

    pricing = MODEL_PRICING.get(model)

    if pricing is None:
        return None

    input_cost = (
        input_tokens / 1_000_000
    ) * pricing["input_per_1m"]

    output_cost = (
        output_tokens / 1_000_000
    ) * pricing["output_per_1m"]

    return input_cost + output_cost