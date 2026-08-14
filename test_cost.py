from controlplane.cost import calculate_cost


cost = calculate_cost(
    model="gpt-4.1-mini",
    input_tokens=1000,
    output_tokens=500,
)

print(f"Estimated cost: ${cost:.8f}")