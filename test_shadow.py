from dotenv import load_dotenv

from controlplane.shadow.evaluator import ShadowEvaluator


load_dotenv()


evaluator = ShadowEvaluator()


result = evaluator.evaluate_factuality(
    context=(
        "Customers can request a refund "
        "within 30 days of purchase."
    ),
    output=(
        "Customers can request a refund "
        "within 30 days."
    ),
)


print("Shadow evaluation:")
print(result)