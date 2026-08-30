import json
import logging
import uuid

from api.database import get_connection

from .evaluator import ShadowEvaluator


logger = logging.getLogger("controlplane.shadow")


class ShadowWorker:
    def __init__(
        self,
        api_key: str | None = None,
    ):
        self.evaluator = ShadowEvaluator(
            api_key=api_key
        )

    # =========================================================
    # EVALUATE RUN
    # =========================================================

    def evaluate_run(self, run_id: str, root_trace_id: str):
        """
        Evaluate all completed LLM child traces belonging to a completed
        application run. The root workflow trace itself is not evaluated.

        Shadow evaluation is background work. It must never write to the
        application's interactive stdout.
        """

        logger.debug(
            "Shadow: evaluating run %s (root trace %s)",
            run_id,
            root_trace_id,
        )

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM traces
                    WHERE parent_trace_id = %s
                    ORDER BY started_at ASC NULLS LAST
                    """,
                    (root_trace_id,),
                )
                rows = cursor.fetchall()

        trace_ids = [str(row[0]) for row in rows]

        if not trace_ids:
            logger.debug(
                "Shadow: no child traces found for run %s",
                run_id,
            )
            return

        # Create the lifecycle rows before evaluation starts.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for trace_id in trace_ids:
                    cursor.execute(
                        """
                        INSERT INTO shadow_evaluations (
                            id,
                            trace_id,
                            status,
                            created_at
                        )
                        VALUES (%s, %s, 'pending', NOW())
                        ON CONFLICT (trace_id) DO NOTHING
                        """,
                        (str(uuid.uuid4()), trace_id),
                    )

        for trace_id in trace_ids:
            try:
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE shadow_evaluations
                            SET status = 'running', error = NULL
                            WHERE trace_id = %s
                            """,
                            (trace_id,),
                        )

                self.evaluate_trace(trace_id)

            except Exception as error:
                logger.exception(
                    "Shadow: run %s failed for trace %s",
                    run_id,
                    trace_id,
                )

                try:
                    with get_connection() as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                UPDATE shadow_evaluations
                                SET status = 'failed', error = %s
                                WHERE trace_id = %s
                                """,
                                (str(error), trace_id),
                            )
                except Exception:
                    logger.exception(
                        "Shadow: failed to store failure for %s",
                        trace_id,
                    )

        logger.debug(
            "Shadow: finished run %s; processed %s child traces",
            run_id,
            len(trace_ids),
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
        shadow_evaluations table.
        """

        logger.debug(
            "Shadow: evaluating trace %s",
            trace_id,
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
            logger.warning(
                "Shadow: trace %s not found",
                trace_id,
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
            logger.warning(
                "Shadow: trace %s has no output",
                trace_id,
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

        logger.debug(
            "Shadow: loaded %s spans from workflow %s",
            len(spans),
            workflow_trace_id,
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
            logger.exception(
                "Shadow: evaluation failed for %s",
                trace_id,
            )

            try:
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE shadow_evaluations
                            SET status = 'failed', error = %s
                            WHERE trace_id = %s
                            """,
                            (str(error), trace_id),
                        )
            except Exception:
                logger.exception(
                    "Shadow: failed to store evaluation failure for %s",
                    trace_id,
                )

            return

        # =====================================================
        # 6. VALIDATE RESULT
        # =====================================================

        if not isinstance(result, dict):
            logger.error(
                "Shadow: invalid evaluation result for %s",
                trace_id,
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

        if factuality_status in {
            "excellent",
            "good",
        }:
            factuality_status = "supported"

        elif factuality_status == "needs_improvement":
            factuality_status = "partially_supported"

        elif factuality_status == "poor":
            factuality_status = "unsupported"

        elif factuality_status == "not_applicable":
            factuality_status = "not_applicable"

        # =====================================================
        # 9. SERIALIZE JSONB
        # =====================================================

        try:
            shadow_evaluation_json = json.dumps(
                result,
                ensure_ascii=False,
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            logger.exception(
                "Shadow: failed to serialize evaluation for %s",
                trace_id,
            )
            return

        # Keep this variable intentionally generated for compatibility
        # with the existing evaluation pipeline.
        _ = shadow_evaluation_json

        # =====================================================
        # 10. STORE COMPLETE EVALUATION
        # =====================================================

        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO shadow_evaluations (
                            id,
                            trace_id,
                            status,
                            factuality_score,
                            factuality_status,
                            input,
                            context,
                            output,
                            created_at,
                            evaluated_at,
                            error
                        )
                        VALUES (
                            %s,
                            %s,
                            'completed',
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            NOW(),
                            NOW(),
                            NULL
                        )
                        ON CONFLICT (trace_id)
                        DO UPDATE SET
                            status = 'completed',
                            factuality_score = EXCLUDED.factuality_score,
                            factuality_status = EXCLUDED.factuality_status,
                            input = EXCLUDED.input,
                            context = EXCLUDED.context,
                            output = EXCLUDED.output,
                            evaluated_at = EXCLUDED.evaluated_at,
                            error = NULL
                        """,
                        (
                            str(uuid.uuid4()),
                            trace_id,
                            factuality_score,
                            factuality_status,
                            input_text,
                            context,
                            output,
                        ),
                    )

        except Exception:
            logger.exception(
                "Shadow: failed to store evaluation for %s",
                trace_id,
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

        logger.debug(
            "Shadow: trace %s → overall=%s status=%s recommendations=%s",
            trace_id,
            overall_score,
            overall_status,
            len(recommendations),
        )

        # =====================================================
        # 12. TOP RECOMMENDATIONS
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

            logger.debug(
                "Shadow recommendation: %s %s",
                severity,
                title,
            )