import json

from api.database import get_connection

from controlplane.shadow.evaluator import ShadowEvaluator


class ShadowWorker:
    def __init__(
        self,
        api_key: str | None = None,
    ):
        self.evaluator = ShadowEvaluator(
            api_key=api_key
        )

    # =========================================================
    # EVALUATE TRACE
    # =========================================================

    def evaluate_trace(
        self,
        trace_id: str,
    ):
        """
        Evaluate a completed LLM trace.

        Shadow receives:

        - original user input
        - supplied context
        - model output
        - parent workflow spans

        The evaluator produces a structured result containing:

        - grounding / factuality
        - relevance
        - completeness
        - instruction following
        - flow accuracy
        - tool correctness
        - context quality
        - consistency
        - hallucination risk
        - safety
        - overall quality
        - recommendations

        The complete result is stored in the
        traces.shadow_evaluation JSONB column.
        """

        print(
            f"Shadow: evaluating trace {trace_id}"
        )

        # =====================================================
        # 1. LOAD LLM TRACE
        # =====================================================

        with get_connection() as connection:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        parent_trace_id,
                        input,
                        context,
                        output
                    FROM traces
                    WHERE id = %s
                    """,
                    (trace_id,),
                )

                trace = cursor.fetchone()

        if trace is None:
            print(
                f"Shadow: trace {trace_id} not found"
            )
            return

        (
            _,
            parent_trace_id,
            input_text,
            context,
            output,
        ) = trace

        # =====================================================
        # 2. VALIDATE OUTPUT
        # =====================================================

        if not output:
            print(
                f"Shadow: trace {trace_id} has no output"
            )
            return

        # =====================================================
        # 3. DETERMINE WORKFLOW TRACE
        # =====================================================

        workflow_trace_id = (
            parent_trace_id
            if parent_trace_id
            else trace_id
        )

        # =====================================================
        # 4. LOAD WORKFLOW SPANS
        # =====================================================

        with get_connection() as connection:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        parent_span_id,
                        name,
                        span_type,
                        input,
                        output,
                        duration_ms,
                        status,
                        metadata
                    FROM spans
                    WHERE trace_id = %s
                    ORDER BY started_at ASC NULLS LAST
                    """,
                    (workflow_trace_id,),
                )

                rows = cursor.fetchall()

        spans = []

        for row in rows:

            spans.append(
                {
                    "id": str(row[0]),

                    "parent_span_id": (
                        str(row[1])
                        if row[1]
                        else None
                    ),

                    "name": row[2],

                    "span_type": row[3],

                    "input": row[4],

                    "output": row[5],

                    "duration_ms": row[6],

                    "status": row[7],

                    "metadata": row[8] or {},
                }
            )

        print(
            f"Shadow: loaded {len(spans)} spans "
            f"from workflow {workflow_trace_id}"
        )

        # =====================================================
        # 5. RUN SHADOW EVALUATION
        # =====================================================

        try:

            result = self.evaluator.evaluate(
                user_input=input_text or "",
                context=context,
                output=output,
                spans=spans,
            )

        except Exception as error:

            print(
                f"Shadow: evaluation failed for "
                f"{trace_id}: {error}"
            )

            return

        # =====================================================
        # 6. VALIDATE RESULT
        # =====================================================

        if not isinstance(result, dict):

            print(
                f"Shadow: invalid evaluation result "
                f"for {trace_id}"
            )

            return

        # =====================================================
        # 7. EXTRACT GROUNDING
        # =====================================================

        grounding = result.get(
            "grounding",
            {},
        )

        if not isinstance(
            grounding,
            dict,
        ):
            grounding = {}

        factuality_score = grounding.get(
            "score"
        )

        factuality_status = grounding.get(
            "status"
        )

        # =====================================================
        # 8. BACKWARD COMPATIBILITY
        # =====================================================

        if factuality_status == "excellent":

            factuality_status = (
                "supported"
            )

        elif factuality_status == "good":

            factuality_status = (
                "supported"
            )

        elif factuality_status == "needs_improvement":

            factuality_status = (
                "partially_supported"
            )

        elif factuality_status == "poor":

            factuality_status = (
                "unsupported"
            )

        elif factuality_status == "not_applicable":

            factuality_status = (
                "not_applicable"
            )

        # =====================================================
        # 9. SERIALIZE JSONB
        # =====================================================

        try:

            shadow_evaluation_json = (
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
            )

        except (
            TypeError,
            ValueError,
        ) as error:

            print(
                f"Shadow: failed to serialize "
                f"evaluation for {trace_id}: "
                f"{error}"
            )

            return

        # =====================================================
        # 10. STORE COMPLETE EVALUATION
        # =====================================================

        try:

            with get_connection() as connection:

                with connection.cursor() as cursor:

                    cursor.execute(
                        """
                        UPDATE traces
                        SET
                            factuality_score = %s,
                            factuality_status = %s,
                            shadow_evaluation = %s,
                            evaluated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            factuality_score,
                            factuality_status,
                            shadow_evaluation_json,
                            trace_id,
                        ),
                    )

        except Exception as error:

            print(
                f"Shadow: failed to store evaluation "
                f"for {trace_id}: {error}"
            )

            return

        # =====================================================
        # 11. SUMMARY
        # =====================================================

        overall = result.get(
            "overall",
            {},
        )

        if not isinstance(
            overall,
            dict,
        ):
            overall = {}

        overall_score = overall.get(
            "score"
        )

        overall_status = overall.get(
            "status"
        )

        recommendations = result.get(
            "recommendations",
            [],
        )

        if not isinstance(
            recommendations,
            list,
        ):
            recommendations = []

        print(
            f"Shadow: trace {trace_id} → "
            f"overall={overall_score} "
            f"status={overall_status} "
            f"recommendations={len(recommendations)}"
        )

        # =====================================================
        # 12. PRINT TOP RECOMMENDATIONS
        # =====================================================

        for recommendation in recommendations[:3]:

            if not isinstance(
                recommendation,
                dict,
            ):
                continue

            severity = recommendation.get(
                "severity",
                "unknown",
            )

            title = recommendation.get(
                "title",
                "Untitled recommendation",
            )

            print(
                "Shadow recommendation:",
                severity,
                title,
            )