from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg.types.json import Jsonb
from uuid import UUID
from fastapi.middleware.cors import CORSMiddleware
from .database import get_connection


app = FastAPI(title="ControlPlane.AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def validate_uuid(
    value: str,
    field_name: str = "ID",
) -> None:
    """Validate that a value is a UUID string."""
    try:
        UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Expected a UUID.",
        )




class TraceCreate(BaseModel):
    id: str
    provider: str
    model: str
    input: str
    output: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    estimated_cost_usd: float | None = None
    context: str | None = None
    session_id: str | None = None
    status: str = "success"
    safety_flag: bool = False
    safety_type: str | None = None
    safety_action: str | None = None
    parent_trace_id: str | None = None


class SpanCreate(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    span_type: str
    duration_ms: int | None = None
    status: str = "success"
    metadata: dict | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


# ============================================================
# CREATE TRACE
# ============================================================

@app.post("/traces")
def create_trace(trace: TraceCreate):

    trace_id = trace.id

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO traces (
                    id,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    session_id,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    parent_trace_id
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s
                )
                """,
                (
                    trace_id,
                    trace.provider,
                    trace.model,
                    trace.input,
                    trace.output,
                    trace.input_tokens,
                    trace.output_tokens,
                    trace.latency_ms,
                    trace.estimated_cost_usd,
                    trace.context,
                    trace.session_id,
                    trace.status,
                    trace.safety_flag,
                    trace.safety_type,
                    trace.safety_action,
                    trace.parent_trace_id,
                ),
            )

    return {
        "id": trace_id,
        "status": "created",
    }


# ============================================================
# LIST TRACES
# ============================================================

@app.get("/traces")
def get_traces(
    limit: int = 50,
    offset: int = 0,
):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    created_at,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    session_id,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    parent_trace_id,
                    factuality_score,
                    factuality_status,
                    evaluated_at
                FROM traces
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )

            rows = cursor.fetchall()

    return [
        {
            "id": str(row[0]),
            "created_at": row[1],
            "provider": row[2],
            "model": row[3],
            "input": row[4],
            "output": row[5],
            "input_tokens": row[6],
            "output_tokens": row[7],
            "latency_ms": row[8],
            "estimated_cost_usd": row[9],
            "context": row[10],
            "session_id": row[11],
            "status": row[12],
            "safety_flag": row[13],
            "safety_type": row[14],
            "safety_action": row[15],
            "parent_trace_id": str(row[16]) if row[16] else None,
            "factuality_score": row[17],
            "factuality_status": row[18],
            "evaluated_at": row[19],
        }
        for row in rows
    ]


# ============================================================
# METRICS
# ============================================================

@app.get("/metrics")
def get_metrics():
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(AVG(latency_ms), 0),
                    COALESCE(SUM(estimated_cost_usd), 0),

                    COUNT(*) FILTER (
                        WHERE status = 'blocked'
                    ),

                    COUNT(*) FILTER (
                        WHERE factuality_status = 'unsupported'
                    ),

                    COUNT(*) FILTER (
                        WHERE factuality_status = 'partially_supported'
                    ),

                    COUNT(*) FILTER (
                        WHERE factuality_status = 'supported'
                    )

                FROM traces
                """
            )

            row = cursor.fetchone()

    return {
        "total_requests": row[0],
        "average_latency_ms": float(row[1]),
        "total_cost_usd": float(row[2]),
        "blocked_requests": row[3],
        "unsupported_responses": row[4],
        "partially_supported_responses": row[5],
        "supported_responses": row[6],
    }


# ============================================================
# CREATE SPAN
# ============================================================

@app.post("/spans")
def create_span(span: SpanCreate):

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO spans (
                    id,
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    duration_ms,
                    status,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.name,
                    span.span_type,
                    span.duration_ms,
                    span.status,
                    Jsonb(span.metadata or {}),
                ),
            )

    return {
        "id": span.span_id,
        "trace_id": span.trace_id,
        "status": "created",
    }


# ============================================================
# GET FLAT SPANS
# ============================================================

@app.get("/spans/{trace_id}")
def get_spans(trace_id: str):

    # Validate UUID before sending it to PostgreSQL.
    try:
        UUID(trace_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid trace ID. Expected a UUID.",
        )

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    started_at,
                    ended_at,
                    duration_ms,
                    status,
                    metadata
                FROM spans
                WHERE trace_id = %s
                ORDER BY started_at ASC
                """,
                (trace_id,),
            )

            rows = cursor.fetchall()

    return [
        {
            "id": str(row[0]),
            "trace_id": str(row[1]),
            "parent_span_id": (
                str(row[2]) if row[2] else None
            ),
            "name": row[3],
            "span_type": row[4],
            "started_at": row[5],
            "ended_at": row[6],
            "duration_ms": row[7],
            "status": row[8],
            "metadata": row[9] or {},
        }
        for row in rows
    ]


# ============================================================
# GET COMPLETE TRACE WITH NESTED SPANS
# ============================================================

@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):

    # --------------------------------------------------------
    # 1. Validate UUID
    # --------------------------------------------------------

    try:
        UUID(trace_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid trace ID. Expected a UUID.",
        )

    # --------------------------------------------------------
    # 2. Get trace and spans
    # --------------------------------------------------------

    with get_connection() as connection:
        with connection.cursor() as cursor:

            # ------------------------------------------------
            # Get the main trace
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    created_at,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    session_id,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    parent_trace_id,
                    factuality_score,
                    factuality_status,
                    evaluated_at
                FROM traces
                WHERE id = %s
                """,
                (trace_id,),
            )

            trace_row = cursor.fetchone()

            # ------------------------------------------------
            # Trace doesn't exist
            # ------------------------------------------------

            if trace_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Trace not found.",
                )

            # ------------------------------------------------
            # Get all spans
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    started_at,
                    ended_at,
                    duration_ms,
                    status,
                    metadata
                FROM spans
                WHERE trace_id = %s
                ORDER BY started_at ASC
                """,
                (trace_id,),
            )

            span_rows = cursor.fetchall()

    # --------------------------------------------------------
    # 3. Convert database rows into span objects
    # --------------------------------------------------------

    spans = []

    for row in span_rows:

        spans.append(
            {
                "id": str(row[0]),
                "trace_id": str(row[1]),
                "parent_span_id": (
                    str(row[2])
                    if row[2]
                    else None
                ),
                "name": row[3],
                "span_type": row[4],
                "started_at": row[5],
                "ended_at": row[6],
                "duration_ms": row[7],
                "status": row[8],
                "metadata": row[9] or {},
                "children": [],
            }
        )

    # --------------------------------------------------------
    # 4. Create lookup table
    # --------------------------------------------------------

    span_map = {
        span["id"]: span
        for span in spans
    }

    # --------------------------------------------------------
    # 5. Build parent → child relationships
    # --------------------------------------------------------

    roots = []

    for span in spans:

        parent_id = span["parent_span_id"]

        if parent_id and parent_id in span_map:

            span_map[parent_id]["children"].append(
                span
            )

        else:

            roots.append(span)

    # --------------------------------------------------------
    # 6. Return complete trace
    # --------------------------------------------------------

    return {
        "trace": {
            "id": str(trace_row[0]),
            "created_at": trace_row[1],
            "provider": trace_row[2],
            "model": trace_row[3],
            "input": trace_row[4],
            "output": trace_row[5],
            "input_tokens": trace_row[6],
            "output_tokens": trace_row[7],
            "latency_ms": trace_row[8],
            "estimated_cost_usd": trace_row[9],
            "context": trace_row[10],
            "session_id": trace_row[11],
            "status": trace_row[12],
            "safety_flag": trace_row[13],
            "safety_type": trace_row[14],
            "safety_action": trace_row[15],
            "parent_trace_id": (
                str(trace_row[16]) if trace_row[16] else None
            ),
            "factuality_score": trace_row[17],
            "factuality_status": trace_row[18],
            "evaluated_at": trace_row[19],
        },
        "spans": roots,
    }


# ============================================================
# ANALYTICS
# ============================================================

@app.get("/analytics")
def get_analytics():

    with get_connection() as connection:
        with connection.cursor() as cursor:

            # ------------------------------------------------
            # 1. Overall request metrics
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(AVG(latency_ms), 0),
                    COALESCE(SUM(estimated_cost_usd), 0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0),

                    COUNT(*) FILTER (
                        WHERE status = 'success'
                    ),

                    COUNT(*) FILTER (
                        WHERE status = 'error'
                    ),

                    COUNT(*) FILTER (
                        WHERE status = 'blocked'
                    )

                FROM traces
                """
            )

            overall = cursor.fetchone()

            # ------------------------------------------------
            # 2. Model breakdown
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    model,
                    COUNT(*),
                    COALESCE(AVG(latency_ms), 0),
                    COALESCE(SUM(estimated_cost_usd), 0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0)
                FROM traces
                WHERE provider = 'openai'
                GROUP BY model
                ORDER BY COUNT(*) DESC
                """
            )

            model_rows = cursor.fetchall()

            # ------------------------------------------------
            # 3. Span analytics
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    span_type,
                    COUNT(*),
                    COALESCE(AVG(duration_ms), 0),
                    COALESCE(SUM(duration_ms), 0)
                FROM spans
                GROUP BY span_type
                ORDER BY COUNT(*) DESC
                """
            )

            span_rows = cursor.fetchall()

            # ------------------------------------------------
            # 4. Slowest spans
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    trace_id,
                    name,
                    span_type,
                    duration_ms,
                    status
                FROM spans
                WHERE duration_ms IS NOT NULL
                ORDER BY duration_ms DESC
                LIMIT 10
                """
            )

            slow_rows = cursor.fetchall()

            # ------------------------------------------------
            # 5. Most expensive requests
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    model,
                    estimated_cost_usd,
                    input_tokens,
                    output_tokens,
                    latency_ms
                FROM traces
                WHERE estimated_cost_usd IS NOT NULL
                ORDER BY estimated_cost_usd DESC
                LIMIT 10
                """
            )

            expensive_rows = cursor.fetchall()

    # --------------------------------------------------------
    # Return analytics
    # --------------------------------------------------------

    return {
        "overview": {
            "total_requests": overall[0],
            "average_latency_ms": float(overall[1]),
            "total_cost_usd": float(overall[2]),
            "total_input_tokens": overall[3],
            "total_output_tokens": overall[4],
            "successful_requests": overall[5],
            "error_requests": overall[6],
            "blocked_requests": overall[7],
        },

        "models": [
            {
                "model": row[0],
                "requests": row[1],
                "average_latency_ms": float(row[2]),
                "total_cost_usd": float(row[3]),
                "input_tokens": row[4],
                "output_tokens": row[5],
            }
            for row in model_rows
        ],

        "spans": [
            {
                "span_type": row[0],
                "count": row[1],
                "average_duration_ms": float(row[2]),
                "total_duration_ms": row[3],
            }
            for row in span_rows
        ],

        "slowest_spans": [
            {
                "trace_id": str(row[0]),
                "name": row[1],
                "span_type": row[2],
                "duration_ms": row[3],
                "status": row[4],
            }
            for row in slow_rows
        ],

        "most_expensive_requests": [
            {
                "trace_id": str(row[0]),
                "model": row[1],
                "estimated_cost_usd": float(row[2]),
                "input_tokens": row[3],
                "output_tokens": row[4],
                "latency_ms": row[5],
            }
            for row in expensive_rows
        ],
    }

# ============================================================
# WORKFLOW BOTTLENECK ANALYSIS
# ============================================================

# ============================================================
# WORKFLOW BOTTLENECK / CRITICAL PATH ANALYSIS
# ============================================================

@app.get("/traces/{trace_id}/analysis")
def analyze_trace(trace_id: str):

    # --------------------------------------------------------
    # 1. Validate UUID
    # --------------------------------------------------------

    try:
        UUID(trace_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid trace ID. Expected a UUID.",
        )

    # --------------------------------------------------------
    # 2. Load trace + spans
    # --------------------------------------------------------

    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    latency_ms,
                    status
                FROM traces
                WHERE id = %s
                """,
                (trace_id,),
            )

            trace_row = cursor.fetchone()

            if trace_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Trace not found.",
                )

            cursor.execute(
                """
                SELECT
                    id,
                    parent_span_id,
                    name,
                    span_type,
                    duration_ms,
                    status
                FROM spans
                WHERE trace_id = %s
                  AND duration_ms IS NOT NULL
                """,
                (trace_id,),
            )

            span_rows = cursor.fetchall()

    # --------------------------------------------------------
    # 3. No spans
    # --------------------------------------------------------

    if not span_rows:
        return {
            "trace_id": trace_id,
            "workflow_latency_ms": trace_row[1],
            "critical_path_ms": 0,
            "critical_path": [],
            "total_span_duration_ms": 0,
            "span_count": 0,
            "bottlenecks": [],
        }

    # --------------------------------------------------------
    # 4. Build span nodes
    # --------------------------------------------------------

    spans = {}

    for row in span_rows:

        span_id = str(row[0])

        spans[span_id] = {
            "id": span_id,
            "parent_span_id": (
                str(row[1])
                if row[1]
                else None
            ),
            "name": row[2],
            "span_type": row[3],
            "duration_ms": row[4],
            "status": row[5],
            "children": [],
        }

    # --------------------------------------------------------
    # 5. Build tree
    # --------------------------------------------------------

    roots = []

    for span in spans.values():

        parent_id = span["parent_span_id"]

        if (
            parent_id
            and parent_id in spans
        ):
            spans[parent_id]["children"].append(
                span["id"]
            )
        else:
            roots.append(span["id"])

    # --------------------------------------------------------
    # 6. Calculate longest path recursively
    # --------------------------------------------------------

    memo = {}

    def calculate_path(span_id):

        if span_id in memo:
            return memo[span_id]

        span = spans[span_id]

        duration = span["duration_ms"]

        if not span["children"]:
            result = {
                "duration_ms": duration,
                "path": [span_id],
            }

            memo[span_id] = result
            return result

        best_child = None

        for child_id in span["children"]:

            child_result = calculate_path(
                child_id
            )

            if (
                best_child is None
                or child_result["duration_ms"]
                > best_child["duration_ms"]
            ):
                best_child = child_result

        result = {
            "duration_ms": (
                duration
                + best_child["duration_ms"]
            ),
            "path": [
                span_id,
                *best_child["path"],
            ],
        }

        memo[span_id] = result

        return result

    # --------------------------------------------------------
    # 7. Find global critical path
    # --------------------------------------------------------

    best_path = None

    for root_id in roots:

        result = calculate_path(root_id)

        if (
            best_path is None
            or result["duration_ms"]
            > best_path["duration_ms"]
        ):
            best_path = result

    # --------------------------------------------------------
    # 8. Convert critical path IDs to useful objects
    # --------------------------------------------------------

    critical_path = []

    for span_id in best_path["path"]:

        span = spans[span_id]

        critical_path.append(
            {
                "span_id": span["id"],
                "name": span["name"],
                "span_type": span["span_type"],
                "duration_ms": span["duration_ms"],
                "status": span["status"],
            }
        )

    # --------------------------------------------------------
    # 9. Calculate total span duration
    # --------------------------------------------------------

    total_span_duration_ms = sum(
        span["duration_ms"]
        for span in spans.values()
    )

    # --------------------------------------------------------
    # 10. Calculate bottleneck percentages
    # --------------------------------------------------------

    bottlenecks = []

    for span in spans.values():

        percentage = 0.0

        if total_span_duration_ms > 0:
            percentage = (
                span["duration_ms"]
                / total_span_duration_ms
            ) * 100

        bottlenecks.append(
            {
                "span_id": span["id"],
                "parent_span_id": span[
                    "parent_span_id"
                ],
                "name": span["name"],
                "span_type": span["span_type"],
                "duration_ms": span["duration_ms"],
                "percentage_of_total_span_time": round(
                    percentage,
                    2,
                ),
                "on_critical_path": (
                    span["id"]
                    in best_path["path"]
                ),
                "status": span["status"],
            }
        )

    # Longest spans first.
    bottlenecks.sort(
        key=lambda item: item["duration_ms"],
        reverse=True,
    )

    # --------------------------------------------------------
    # 11. Return analysis
    # --------------------------------------------------------

    return {
        "trace_id": trace_id,
        "workflow_latency_ms": trace_row[1],
        "critical_path_ms": best_path[
            "duration_ms"
        ],
        "critical_path": critical_path,
        "total_span_duration_ms": (
            total_span_duration_ms
        ),
        "span_count": len(spans),
        "bottlenecks": bottlenecks,
    }

# ============================================================
# WORKFLOW INSIGHTS
# ============================================================

@app.get("/traces/{trace_id}/insights")
def get_trace_insights(trace_id: str):

    # --------------------------------------------------------
    # 1. Validate UUID
    # --------------------------------------------------------

    try:
        UUID(trace_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid trace ID. Expected a UUID.",
        )

    # --------------------------------------------------------
    # 2. Load workflow trace, spans, and Shadow evaluations
    # --------------------------------------------------------

    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    provider,
                    model,
                    latency_ms,
                    estimated_cost_usd,
                    status,
                    parent_trace_id
                FROM traces
                WHERE id = %s
                """,
                (trace_id,),
            )

            trace_row = cursor.fetchone()

            if trace_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Trace not found.",
                )

            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    span_type,
                    duration_ms,
                    status
                FROM spans
                WHERE trace_id = %s
                  AND duration_ms IS NOT NULL
                ORDER BY duration_ms DESC
                """,
                (trace_id,),
            )

            span_rows = cursor.fetchall()

            # Shadow evaluations are stored as child traces whose
            # parent_trace_id points at this workflow trace.
            cursor.execute(
                """
                SELECT
                    id,
                    provider,
                    model,
                    input,
                    output,
                    context,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    status,
                    factuality_score,
                    factuality_status,
                    evaluated_at
                FROM traces
                WHERE parent_trace_id = %s
                ORDER BY created_at DESC
                """,
                (trace_id,),
            )

            shadow_rows = cursor.fetchall()

    # --------------------------------------------------------
    # 3. Build Shadow evaluation objects
    # --------------------------------------------------------

    shadow_evaluations = []

    for row in shadow_rows:
        shadow_evaluations.append(
            {
                "trace_id": str(row[0]),
                "provider": row[1],
                "model": row[2],
                "input": row[3],
                "has_output": row[4] is not None and row[4] != "",
                "context": row[5],
                "input_tokens": row[6],
                "output_tokens": row[7],
                "latency_ms": row[8],
                "estimated_cost_usd": (
                    float(row[9]) if row[9] is not None else None
                ),
                "status": row[10],
                "factuality_score": (
                    float(row[11]) if row[11] is not None else None
                ),
                "factuality_status": row[12],
                "evaluated_at": row[13],
            }
        )

    # --------------------------------------------------------
    # 4. Aggregate Shadow quality
    # --------------------------------------------------------

    evaluated_shadow = [
        item
        for item in shadow_evaluations
        if item["factuality_status"] is not None
    ]

    shadow_summary = {
        "evaluations": len(shadow_evaluations),
        "evaluated": len(evaluated_shadow),
        "average_factuality_score": None,
        "supported": 0,
        "partially_supported": 0,
        "unsupported": 0,
        "pending": len(shadow_evaluations) - len(evaluated_shadow),
    }

    if evaluated_shadow:
        shadow_summary["average_factuality_score"] = round(
            sum(
                item["factuality_score"]
                for item in evaluated_shadow
                if item["factuality_score"] is not None
            )
            / max(
                1,
                sum(
                    1
                    for item in evaluated_shadow
                    if item["factuality_score"] is not None
                ),
            ),
            3,
        )

        for item in evaluated_shadow:
            status = item["factuality_status"]

            if status == "supported":
                shadow_summary["supported"] += 1
            elif status == "partially_supported":
                shadow_summary["partially_supported"] += 1
            elif status == "unsupported":
                shadow_summary["unsupported"] += 1

    # --------------------------------------------------------
    # 5. No spans
    # --------------------------------------------------------

    if not span_rows:
        recommendations = []

        if shadow_summary["unsupported"] > 0:
            recommendations.append(
                "Shadow evaluation found an unsupported response; improve grounding "
                "or retrieval before generating the answer."
            )
        elif shadow_summary["partially_supported"] > 0:
            recommendations.append(
                "Shadow evaluation found a partially supported response; improve "
                "grounding or provide more relevant context."
            )

        if shadow_summary["pending"] > 0:
            recommendations.append(
                "Shadow evaluation is still pending for one or more child traces."
            )

        return {
            "trace_id": trace_id,
            "summary": (
                "No spans were recorded for this trace."
            ),
            "bottleneck": None,
            "duration_ms": None,
            "latency_share": 0,
            "workflow_latency_ms": trace_row[3],
            "cost_usd": (
                float(trace_row[4])
                if trace_row[4] is not None
                else None
            ),
            "shadow": shadow_summary,
            "shadow_evaluations": shadow_evaluations,
            "recommendations": recommendations,
        }

    # --------------------------------------------------------
    # 6. Find primary latency bottleneck
    # --------------------------------------------------------

    bottleneck = span_rows[0]

    bottleneck_id = str(bottleneck[0])
    bottleneck_name = bottleneck[1]
    bottleneck_type = bottleneck[2]
    bottleneck_duration = bottleneck[3]

    total_span_duration = sum(
        row[3]
        for row in span_rows
    )

    latency_share = 0.0

    if total_span_duration > 0:
        latency_share = (
            bottleneck_duration
            / total_span_duration
        ) * 100

    # --------------------------------------------------------
    # 7. Generate performance recommendations
    # --------------------------------------------------------

    performance_recommendations = []

    if bottleneck_type == "llm":
        performance_recommendations.append(
            "Consider reducing prompt size or unnecessary context."
        )
        performance_recommendations.append(
            "Consider using a faster model when response quality permits."
        )
        performance_recommendations.append(
            "Consider caching reusable context or repeated requests."
        )

    elif bottleneck_type == "retrieval":
        performance_recommendations.append(
            "Consider optimizing retrieval latency."
        )
        performance_recommendations.append(
            "Consider caching frequently requested data."
        )
        performance_recommendations.append(
            "Consider reducing the amount of retrieved data."
        )

    elif bottleneck_type == "database":
        performance_recommendations.append(
            "Consider optimizing the database query."
        )
        performance_recommendations.append(
            "Check indexes and query execution time."
        )
        performance_recommendations.append(
            "Consider caching frequently accessed records."
        )

    elif bottleneck_type == "agent":
        performance_recommendations.append(
            "Break the agent workflow into smaller spans."
        )
        performance_recommendations.append(
            "Inspect child spans to identify the underlying bottleneck."
        )

    else:
        performance_recommendations.append(
            "Inspect this span and its children for latency optimization opportunities."
        )

    if bottleneck[4] == "error":
        performance_recommendations.insert(
            0,
            "This bottleneck ended with an error; investigate the failing operation first.",
        )

    # --------------------------------------------------------
    # 8. Generate Shadow / output-quality recommendations
    # --------------------------------------------------------

    quality_recommendations = []

    if shadow_summary["unsupported"] > 0:
        quality_recommendations.append(
            "Shadow evaluation found an unsupported response. "
            "Improve grounding, retrieval quality, or context coverage."
        )

    if shadow_summary["partially_supported"] > 0:
        quality_recommendations.append(
            "Shadow evaluation found a partially supported response. "
            "Improve grounding or provide more relevant supporting context."
        )

    if shadow_summary["supported"] > 0 and not quality_recommendations:
        quality_recommendations.append(
            "Shadow evaluation found the response supported by the provided context."
        )

    if shadow_summary["pending"] > 0:
        quality_recommendations.append(
            "One or more Shadow evaluations are still pending."
        )

    # --------------------------------------------------------
    # 9. Combined recommendations
    # --------------------------------------------------------

    recommendations = (
        performance_recommendations
        + quality_recommendations
    )

    # --------------------------------------------------------
    # 10. Summary
    # --------------------------------------------------------

    summary = (
        f"{bottleneck_name} is the primary latency bottleneck, "
        f"accounting for {latency_share:.1f}% of recorded span time."
    )

    if shadow_summary["average_factuality_score"] is not None:
        summary += (
            f" Shadow factuality score: "
            f"{shadow_summary['average_factuality_score']:.2f}."
        )

    # --------------------------------------------------------
    # 11. Return combined insights
    # --------------------------------------------------------

    return {
        "trace_id": trace_id,

        "summary": summary,

        "performance": {
            "workflow_latency_ms": trace_row[3],
            "cost_usd": (
                float(trace_row[4])
                if trace_row[4] is not None
                else None
            ),
            "bottleneck": {
                "span_id": bottleneck_id,
                "name": bottleneck_name,
                "span_type": bottleneck_type,
                "duration_ms": bottleneck_duration,
                "latency_share": round(
                    latency_share,
                    2,
                ),
                "status": bottleneck[4],
            },
        },

        "shadow": shadow_summary,

        "shadow_evaluations": shadow_evaluations,

        "recommendations": recommendations,

        "performance_recommendations": (
            performance_recommendations
        ),

        "quality_recommendations": (
            quality_recommendations
        ),
    }


# ============================================================
# SESSION / WORKFLOW ANALYTICS
# ============================================================

@app.get("/sessions/{session_id}")
def get_session(session_id: str):

    with get_connection() as connection:
        with connection.cursor() as cursor:

            # ------------------------------------------------
            # 1. Session overview
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(AVG(latency_ms), 0),
                    COALESCE(SUM(estimated_cost_usd), 0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0),

                    COUNT(*) FILTER (
                        WHERE status = 'success'
                    ),

                    COUNT(*) FILTER (
                        WHERE status = 'error'
                    ),

                    COUNT(*) FILTER (
                        WHERE status = 'blocked'
                    )

                FROM traces
                WHERE session_id = %s
                """,
                (session_id,),
            )

            overview = cursor.fetchone()

            # ------------------------------------------------
            # 2. Individual workflows
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    created_at,
                    provider,
                    model,
                    latency_ms,
                    estimated_cost_usd,
                    input_tokens,
                    output_tokens,
                    status
                FROM traces
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            )

            trace_rows = cursor.fetchall()

    # --------------------------------------------------------
    # 3. No session
    # --------------------------------------------------------

    if overview[0] == 0:
        raise HTTPException(
            status_code=404,
            detail="Session not found.",
        )

    # --------------------------------------------------------
    # 4. Build workflow list
    # --------------------------------------------------------

    workflows = [
        {
            "trace_id": str(row[0]),
            "created_at": row[1],
            "provider": row[2],
            "model": row[3],
            "latency_ms": row[4],
            "estimated_cost_usd": (
                float(row[5])
                if row[5] is not None
                else None
            ),
            "input_tokens": row[6],
            "output_tokens": row[7],
            "status": row[8],
        }
        for row in trace_rows
    ]

    # --------------------------------------------------------
    # 5. Find slowest workflow
    # --------------------------------------------------------

    slowest = max(
        workflows,
        key=lambda item: (
            item["latency_ms"] or 0
        ),
    )

    # --------------------------------------------------------
    # 6. Find most expensive workflow
    # --------------------------------------------------------

    most_expensive = max(
        workflows,
        key=lambda item: (
            item["estimated_cost_usd"] or 0
        ),
    )

    # --------------------------------------------------------
    # 7. Return session analytics
    # --------------------------------------------------------

    return {
        "session_id": session_id,

        "overview": {
            "workflow_count": overview[0],
            "average_latency_ms": float(
                overview[1]
            ),
            "total_cost_usd": float(
                overview[2]
            ),
            "total_input_tokens": overview[3],
            "total_output_tokens": overview[4],
            "successful_workflows": overview[5],
            "error_workflows": overview[6],
            "blocked_workflows": overview[7],
        },

        "slowest_workflow": slowest,

        "most_expensive_workflow": (
            most_expensive
        ),

        "workflows": workflows,
    }

@app.patch("/traces/{trace_id}")
def update_trace(
    trace_id: str,
    payload: dict,
):
    """
    Update workflow trace lifecycle fields.

    Supported fields:
    - started_at
    - ended_at
    - latency_ms
    - status
    """

    validate_uuid(
        trace_id,
        "trace ID",
    )

    started_at = payload.get("started_at")
    ended_at = payload.get("ended_at")
    latency_ms = payload.get("latency_ms")
    status = payload.get("status")

    # ---------------------------------------------------------
    # VALIDATE STATUS
    # ---------------------------------------------------------

    allowed_statuses = {
        "pending",
        "running",
        "success",
        "error",
        "blocked",
    }

    if (
        status is not None
        and status not in allowed_statuses
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid status: {status}. "
                f"Allowed values: "
                f"{sorted(allowed_statuses)}"
            ),
        )

    # ---------------------------------------------------------
    # BUILD UPDATE
    # ---------------------------------------------------------

    fields = []
    values = []

    if started_at is not None:
        fields.append(
            "started_at = %s"
        )
        values.append(started_at)

    if ended_at is not None:
        fields.append(
            "ended_at = %s"
        )
        values.append(ended_at)

    if latency_ms is not None:
        fields.append(
            "latency_ms = %s"
        )
        values.append(latency_ms)

    if status is not None:
        fields.append(
            "status = %s"
        )
        values.append(status)

    if not fields:
        raise HTTPException(
            status_code=400,
            detail="No valid fields supplied.",
        )

    values.append(trace_id)

    query = f"""
        UPDATE traces
        SET {", ".join(fields)}
        WHERE id = %s
        RETURNING
            id,
            status,
            started_at,
            ended_at,
            latency_ms
    """

    # ---------------------------------------------------------
    # EXECUTE
    # ---------------------------------------------------------

    try:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    query,
                    values,
                )

                row = cursor.fetchone()

    except Exception as error:

        print(
            f"Trace update database error: {error}"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to update trace.",
        )

    # ---------------------------------------------------------
    # TRACE NOT FOUND
    # ---------------------------------------------------------

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Trace not found.",
        )

    # ---------------------------------------------------------
    # RESPONSE
    # ---------------------------------------------------------

    return {
        "id": str(row[0]),
        "status": row[1],
        "started_at": row[2],
        "ended_at": row[3],
        "latency_ms": row[4],
    }