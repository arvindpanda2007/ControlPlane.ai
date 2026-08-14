import time

from openai import OpenAI

from api.database import get_connection
from controlplane.shadow.evaluator import ShadowEvaluator


class ShadowWorker:
    def __init__(
        self,
        api_key: str | None = None,
    ):
        self.evaluator = ShadowEvaluator(api_key=api_key)

    def evaluate_trace(self, trace_id: str):
        """
        Evaluate one completed trace in the background.
        """

        # ---------------------------------------------------------
        # 1. Get the trace from PostgreSQL
        # ---------------------------------------------------------

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        context,
                        output
                    FROM traces
                    WHERE id = %s
                    """,
                    (trace_id,),
                )

                trace = cursor.fetchone()

        if trace is None:
            print(f"Shadow: trace {trace_id} not found")
            return

        _, context, output = trace

        # ---------------------------------------------------------
        # 2. Skip traces that cannot be evaluated
        # ---------------------------------------------------------

        if not context:
            print(
                f"Shadow: trace {trace_id} has no context, "
                "skipping factuality evaluation"
            )
            return

        if not output:
            print(
                f"Shadow: trace {trace_id} has no output, "
                "skipping factuality evaluation"
            )
            return

        # ---------------------------------------------------------
        # 3. Run evaluator
        # ---------------------------------------------------------

        print(f"Shadow: evaluating trace {trace_id}")

        try:
            result = self.evaluator.evaluate_factuality(
                context=context,
                output=output,
            )

        except Exception as error:
            print(
                f"Shadow: evaluation failed for {trace_id}: "
                f"{error}"
            )
            return

        # ---------------------------------------------------------
        # 4. Store evaluation result
        # ---------------------------------------------------------

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE traces
                    SET
                        factuality_score = %s,
                        factuality_status = %s,
                        evaluated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        result["score"],
                        result["status"],
                        trace_id,
                    ),
                )

        print(
            f"Shadow: trace {trace_id} → "
            f"{result['status']} "
            f"({result['score']})"
        )