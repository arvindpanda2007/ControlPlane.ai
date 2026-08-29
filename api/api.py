from datetime import datetime
from typing import Any
from uuid import UUID
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from .database import get_connection


import json
app = FastAPI(
    title="ControlPlane.AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REQUEST MODELS
# ============================================================


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

    status: str = "pending"

    safety_flag: bool = False
    safety_type: str | None = None
    safety_action: str | None = None

    parent_trace_id: str | None = None

    started_at: datetime | None = None
    ended_at: datetime | None = None


class TraceUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    status: str | None = None


class SpanCreate(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    name: str
    span_type: str

    # Per-span structured observability payload.
    input: Any | None = None
    context: Any | None = None
    output: Any | None = None

    duration_ms: int | None = Field(default=None, ge=0)
    status: str = "success"

    metadata: dict[str, Any] | None = None


# ============================================================
# VALIDATION HELPERS
# ============================================================


def validate_uuid(
    value: str,
    field_name: str,
) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Expected a UUID.",
        )


def trace_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "created_at": row[1],
        "provider": row[2],
        "model": row[3],
        "input": row[4],
        "output": row[5],
        "input_tokens": row[6],
        "output_tokens": row[7],
        "latency_ms": row[8],
        "estimated_cost_usd": (
            float(row[9])
            if row[9] is not None
            else None
        ),
        "context": row[10],
        "session_id": row[11],
        "status": row[12],
        "safety_flag": row[13],
        "safety_type": row[14],
        "safety_action": row[15],
        "parent_trace_id": (
            str(row[16])
            if row[16]
            else None
        ),
        "factuality_score": (
            float(row[17])
            if row[17] is not None
            else None
        ),
        "factuality_status": row[18],
        "evaluated_at": row[19],
        "started_at": row[20],
        "ended_at": row[21],
    }


TRACE_COLUMNS = """
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
    evaluated_at,
    started_at,
    ended_at
"""


# ============================================================
# HEALTH
# ============================================================


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "controlplane-api",
    }


# ============================================================
# CREATE TRACE
# ============================================================


@app.post("/traces")
def create_trace(trace: TraceCreate):
    validate_uuid(
        trace.id,
        "trace ID",
    )

    if not trace.session_id or not trace.session_id.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Project is required. "
                "This workflow cannot be recorded because no "
                "session_id was provided. "
                "Please assign this workflow to a project."
            ),
        )

    if trace.parent_trace_id:
        validate_uuid(
            trace.parent_trace_id,
            "parent_trace_id",
        )

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
                    parent_trace_id,
                    started_at,
                    ended_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    trace.id,
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
                    trace.started_at,
                    trace.ended_at,
                ),
            )

    return {
        "id": trace.id,
        "status": "created",
    }


# ============================================================
# UPDATE TRACE LIFECYCLE
# ============================================================


@app.patch("/traces/{trace_id}")
def update_trace(
    trace_id: str,
    update: TraceUpdate,
):
    validate_uuid(
        trace_id,
        "trace ID",
    )

    updates = []
    values = []

    if update.started_at is not None:
        updates.append("started_at = %s")
        values.append(update.started_at)

    if update.ended_at is not None:
        updates.append("ended_at = %s")
        values.append(update.ended_at)

    if update.latency_ms is not None:
        updates.append("latency_ms = %s")
        values.append(update.latency_ms)

    if update.status is not None:
        allowed_statuses = {
            "pending",
            "running",
            "success",
            "error",
            "blocked",
        }

        if update.status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid status. Allowed values: "
                    "pending, running, success, error, blocked."
                ),
            )

        updates.append("status = %s")
        values.append(update.status)

    if not updates:
        return {
            "id": trace_id,
            "status": "unchanged",
        }

    values.append(trace_id)

    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                f"""
                UPDATE traces
                SET {", ".join(updates)}
                WHERE id = %s
                """,
                tuple(values),
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Trace not found.",
                )

    return {
        "id": trace_id,
        "status": "updated",
    }


# ============================================================
# LIST TRACES
# ============================================================


@app.get("/traces")
def get_traces(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    provider: str | None = None,
    model: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
):
    conditions = []
    values = []

    if provider:
        conditions.append("provider = %s")
        values.append(provider)

    if model:
        conditions.append("model = %s")
        values.append(model)

    if status:
        conditions.append("status = %s")
        values.append(status)

    if session_id:
        conditions.append("session_id = %s")
        values.append(session_id)

    where_clause = ""

    if conditions:
        where_clause = (
            "WHERE " + " AND ".join(conditions)
        )

    values.extend([
        limit,
        offset,
    ])

    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT
                    {TRACE_COLUMNS}
                FROM traces
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                tuple(values),
            )

            rows = cursor.fetchall()

            # Enrich only workflow/root traces in the global trace list.
            # This does not write anything to the database and does not alter
            # the project/session endpoints or trace lifecycle.
            workflow_ids = [
                row[0]
                for row in rows
                if row[2] == "controlplane"
                and row[3] == "workflow"
            ]

            child_usage = {}

            if workflow_ids:
                cursor.execute(
                    """
                    SELECT
                        parent_trace_id,
                        COALESCE(SUM(input_tokens), 0),
                        COALESCE(SUM(output_tokens), 0),
                        COALESCE(SUM(estimated_cost_usd), 0)
                    FROM traces
                    WHERE parent_trace_id = ANY(%s)
                    GROUP BY parent_trace_id
                    """,
                    (workflow_ids,),
                )

                for parent_id, input_tokens, output_tokens, cost in cursor.fetchall():
                    child_usage[parent_id] = {
                        "input_tokens": input_tokens or 0,
                        "output_tokens": output_tokens or 0,
                        "estimated_cost_usd": float(cost or 0),
                    }

    result = []

    for row in rows:
        trace = trace_to_dict(row)
        usage = child_usage.get(row[0])

        if usage:
            if not trace["input_tokens"] and usage["input_tokens"] > 0:
                trace["input_tokens"] = usage["input_tokens"]

            if not trace["output_tokens"] and usage["output_tokens"] > 0:
                trace["output_tokens"] = usage["output_tokens"]

            if (
                not trace["estimated_cost_usd"]
                and usage["estimated_cost_usd"] > 0
            ):
                trace["estimated_cost_usd"] = usage["estimated_cost_usd"]

        result.append(trace)

    return result


# ============================================================
# GET SINGLE TRACE
# ============================================================


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    validate_uuid(
        trace_id,
        "trace ID",
    )

    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT
                    {TRACE_COLUMNS}
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
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    started_at,
                    ended_at,
                    duration_ms,
                    status,
                    input,
                    output,
                    metadata
                FROM spans
                WHERE trace_id = %s
                ORDER BY started_at ASC
                """,
                (trace_id,),
            )

            span_rows = cursor.fetchall()

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
                "input": _deserialize_span_value(row[9]),
                "context": (row[11] or {}).get("context"),
                "output": _deserialize_span_value(row[10]),
                "metadata": row[11] or {},
                "children": [],
            }
        )

    span_map = {
        span["id"]: span
        for span in spans
    }

    roots = []

    for span in spans:
        parent_id = span["parent_span_id"]

        if (
            parent_id
            and parent_id in span_map
        ):
            span_map[parent_id]["children"].append(
                span
            )
        else:
            roots.append(span)

    return {
        "trace": trace_to_dict(trace_row),
        "spans": roots,
    }


# ============================================================
# CREATE SPAN
# ============================================================


def _serialize_span_value(value):
    """Serialize structured span payloads for the existing text columns."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _deserialize_span_value(value):
    """Restore JSON text to structured values when possible."""
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


@app.post("/spans")
def create_span(span: SpanCreate):
    validate_uuid(
        span.trace_id,
        "trace_id",
    )

    validate_uuid(
        span.span_id,
        "span_id",
    )

    if span.parent_span_id:
        validate_uuid(
            span.parent_span_id,
            "parent_span_id",
        )

    with get_connection() as connection:
        with connection.cursor() as cursor:

            # Make sure the parent trace exists.
            cursor.execute(
                """
                SELECT 1
                FROM traces
                WHERE id = %s
                """,
                (span.trace_id,),
            )

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Parent trace not found.",
                )

            cursor.execute(
                """
                INSERT INTO spans (
                    id,
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    input,
                    output,
                    duration_ms,
                    status,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.name,
                    span.span_type,
                    _serialize_span_value(span.input),
                    _serialize_span_value(span.output),
                    span.duration_ms,
                    span.status,
                    Jsonb(
                        {
                            **(span.metadata or {}),
                            "context": span.context,
                        }
                    ),
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
    validate_uuid(
        trace_id,
        "trace ID",
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
                    input,
                    output,
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
            "input": _deserialize_span_value(row[9]),
            "context": (row[11] or {}).get("context"),
            "output": _deserialize_span_value(row[10]),
            "metadata": row[11] or {},
        }
        for row in rows
    ]


# ============================================================
# DASHBOARD OVERVIEW
# ============================================================


@app.get("/analytics/overview")
def get_analytics_overview():
    """
    Dashboard overview.

    Workflow metrics describe the application/workflow itself.
    LLM metrics describe child model requests separately so
    workflow records are not double-counted.
    Shadow metrics describe factuality evaluations when present.
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE status = 'success'),
                    COUNT(*) FILTER (WHERE status = 'error'),
                    COUNT(*) FILTER (WHERE status = 'blocked'),
                    COUNT(*) FILTER (WHERE status = 'running'),
                    COUNT(*) FILTER (WHERE status = 'pending'),
                    COALESCE(
                        AVG(latency_ms)
                        FILTER (WHERE latency_ms IS NOT NULL), 0
                    )
                FROM traces
                WHERE provider = 'controlplane'
                  AND model = 'workflow'
                """
            )
            workflow = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    percentile_cont(0.50)
                    WITHIN GROUP (ORDER BY latency_ms),
                    percentile_cont(0.95)
                    WITHIN GROUP (ORDER BY latency_ms),
                    percentile_cont(0.99)
                    WITHIN GROUP (ORDER BY latency_ms)
                FROM traces
                WHERE provider = 'controlplane'
                  AND model = 'workflow'
                  AND latency_ms IS NOT NULL
                """
            )
            workflow_percentiles = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE status = 'success'),
                    COUNT(*) FILTER (WHERE status = 'error'),
                    COUNT(*) FILTER (WHERE status = 'blocked'),
                    COUNT(*) FILTER (WHERE status = 'running'),
                    COUNT(*) FILTER (WHERE status = 'pending'),
                    COALESCE(
                        AVG(latency_ms)
                        FILTER (WHERE latency_ms IS NOT NULL), 0
                    ),
                    COALESCE(SUM(estimated_cost_usd), 0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0)
                FROM traces
                WHERE NOT (
                    provider = 'controlplane'
                    AND model = 'workflow'
                )
                """
            )
            llm = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    percentile_cont(0.50)
                    WITHIN GROUP (ORDER BY latency_ms),
                    percentile_cont(0.95)
                    WITHIN GROUP (ORDER BY latency_ms),
                    percentile_cont(0.99)
                    WITHIN GROUP (ORDER BY latency_ms)
                FROM traces
                WHERE NOT (
                    provider = 'controlplane'
                    AND model = 'workflow'
                )
                AND latency_ms IS NOT NULL
                """
            )
            llm_percentiles = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    provider,
                    model,
                    COUNT(*),
                    COUNT(*) FILTER (WHERE status = 'success'),
                    COUNT(*) FILTER (WHERE status = 'error'),
                    COUNT(*) FILTER (WHERE status = 'blocked'),
                    COALESCE(
                        AVG(latency_ms)
                        FILTER (WHERE latency_ms IS NOT NULL), 0
                    ),
                    COALESCE(SUM(estimated_cost_usd), 0),
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0)
                FROM traces
                WHERE parent_trace_id IS NOT NULL
                  AND model IS NOT NULL
                  AND model <> ''
                GROUP BY provider, model
                ORDER BY COUNT(*) DESC
                """
            )
            model_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE factuality_status IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE factuality_status = 'supported'
                    ),
                    COUNT(*) FILTER (
                        WHERE factuality_status = 'partially_supported'
                    ),
                    COUNT(*) FILTER (
                        WHERE factuality_status = 'unsupported'
                    ),
                    COUNT(*) FILTER (
                        WHERE factuality_status IS NULL
                    ),
                    AVG(factuality_score)
                    FILTER (WHERE factuality_score IS NOT NULL)
                FROM traces
                """
            )
            shadow = cursor.fetchone()

    workflow_total = workflow[0] or 0
    workflow_success = workflow[1] or 0
    workflow_errors = workflow[2] or 0
    workflow_blocked = workflow[3] or 0
    workflow_running = workflow[4] or 0
    workflow_pending = workflow[5] or 0

    workflow_completed = (
        workflow_success + workflow_errors + workflow_blocked
    )

    workflow_success_rate = (
        workflow_success / workflow_completed * 100
        if workflow_completed else 0
    )
    workflow_error_rate = (
        workflow_errors / workflow_completed * 100
        if workflow_completed else 0
    )
    workflow_blocked_rate = (
        workflow_blocked / workflow_completed * 100
        if workflow_completed else 0
    )

    llm_total = llm[0] or 0
    llm_success = llm[1] or 0
    llm_errors = llm[2] or 0
    llm_blocked = llm[3] or 0
    llm_running = llm[4] or 0
    llm_pending = llm[5] or 0

    llm_completed = llm_success + llm_errors + llm_blocked

    llm_success_rate = (
        llm_success / llm_completed * 100
        if llm_completed else 0
    )
    llm_error_rate = (
        llm_errors / llm_completed * 100
        if llm_completed else 0
    )
    llm_blocked_rate = (
        llm_blocked / llm_completed * 100
        if llm_completed else 0
    )

    shadow_evaluated = shadow[0] or 0
    shadow_supported = shadow[1] or 0
    shadow_partial = shadow[2] or 0
    shadow_unsupported = shadow[3] or 0
    shadow_pending = shadow[4] or 0
    shadow_scored = (
        shadow_supported + shadow_partial + shadow_unsupported
    )

    return {
        "workflow": {
            "runs": workflow_total,
            "reliability": {
                "successful": workflow_success,
                "errors": workflow_errors,
                "blocked": workflow_blocked,
                "running": workflow_running,
                "pending": workflow_pending,
                "success_rate": round(workflow_success_rate, 2),
                "error_rate": round(workflow_error_rate, 2),
                "blocked_rate": round(workflow_blocked_rate, 2),
            },
            "performance": {
                "average_latency_ms": float(workflow[6] or 0),
                "p50_latency_ms": (
                    float(workflow_percentiles[0])
                    if workflow_percentiles[0] is not None else None
                ),
                "p95_latency_ms": (
                    float(workflow_percentiles[1])
                    if workflow_percentiles[1] is not None else None
                ),
                "p99_latency_ms": (
                    float(workflow_percentiles[2])
                    if workflow_percentiles[2] is not None else None
                ),
            },
        },
        "llm": {
            "requests": llm_total,
            "reliability": {
                "successful": llm_success,
                "errors": llm_errors,
                "blocked": llm_blocked,
                "running": llm_running,
                "pending": llm_pending,
                "success_rate": round(llm_success_rate, 2),
                "error_rate": round(llm_error_rate, 2),
                "blocked_rate": round(llm_blocked_rate, 2),
            },
            "performance": {
                "average_latency_ms": float(llm[6] or 0),
                "p50_latency_ms": (
                    float(llm_percentiles[0])
                    if llm_percentiles[0] is not None else None
                ),
                "p95_latency_ms": (
                    float(llm_percentiles[1])
                    if llm_percentiles[1] is not None else None
                ),
                "p99_latency_ms": (
                    float(llm_percentiles[2])
                    if llm_percentiles[2] is not None else None
                ),
            },
            "cost": {
                "total_cost_usd": float(llm[7] or 0),
            },
            "tokens": {
                "input": llm[8] or 0,
                "output": llm[9] or 0,
                "total": (llm[8] or 0) + (llm[9] or 0),
            },
            "models": [
                {
                    "provider": row[0],
                    "model": row[1],
                    "requests": row[2],
                    "successful": row[3],
                    "errors": row[4],
                    "blocked": row[5],
                    "success_rate": round(
                        row[3] / (row[3] + row[4] + row[5]) * 100,
                        2,
                    ) if (row[3] + row[4] + row[5]) else 0,
                    "average_latency_ms": float(row[6] or 0),
                    "cost_usd": float(row[7] or 0),
                    "input_tokens": row[8] or 0,
                    "output_tokens": row[9] or 0,
                    "total_tokens": (row[8] or 0) + (row[9] or 0),
                }
                for row in model_rows
            ],
        },
        "shadow": {
            "evaluations": shadow_evaluated,
            "scored": shadow_scored,
            "pending": shadow_pending,
            "supported": shadow_supported,
            "partially_supported": shadow_partial,
            "unsupported": shadow_unsupported,
            "average_factuality_score": (
                float(shadow[5]) if shadow[5] is not None else None
            ),
            "supported_rate": round(
                shadow_supported / shadow_scored * 100, 2
            ) if shadow_scored else 0,
            "partially_supported_rate": round(
                shadow_partial / shadow_scored * 100, 2
            ) if shadow_scored else 0,
            "unsupported_rate": round(
                shadow_unsupported / shadow_scored * 100, 2
            ) if shadow_scored else 0,
        },
    }


# ============================================================
# GENERAL ANALYTICS
# ============================================================


@app.get("/analytics")
def get_analytics():
    with get_connection() as connection:
        with connection.cursor() as cursor:

            # ------------------------------------------------
            # Overall
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    COUNT(*),

                    COALESCE(
                        AVG(latency_ms),
                        0
                    ),

                    COALESCE(
                        SUM(estimated_cost_usd),
                        0
                    ),

                    COALESCE(
                        SUM(input_tokens),
                        0
                    ),

                    COALESCE(
                        SUM(output_tokens),
                        0
                    ),

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
            # Models
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    provider,
                    model,
                    COUNT(*),
                    COALESCE(
                        AVG(latency_ms),
                        0
                    ),
                    COALESCE(
                        SUM(estimated_cost_usd),
                        0
                    ),
                    COALESCE(
                        SUM(input_tokens),
                        0
                    ),
                    COALESCE(
                        SUM(output_tokens),
                        0
                    )
                FROM traces
                WHERE parent_trace_id IS NOT NULL
                  AND model IS NOT NULL
                  AND model <> ''
                GROUP BY provider, model
                ORDER BY COUNT(*) DESC
                """
            )

            model_rows = cursor.fetchall()

            # ------------------------------------------------
            # Span analytics
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    span_type,
                    COUNT(*),
                    COALESCE(
                        AVG(duration_ms),
                        0
                    ),
                    COALESCE(
                        SUM(duration_ms),
                        0
                    )
                FROM spans
                GROUP BY span_type
                ORDER BY COUNT(*) DESC
                """
            )

            span_rows = cursor.fetchall()

            # ------------------------------------------------
            # Slowest spans
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
                LIMIT 20
                """
            )

            slow_rows = cursor.fetchall()

            # ------------------------------------------------
            # Expensive requests
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    provider,
                    model,
                    estimated_cost_usd,
                    input_tokens,
                    output_tokens,
                    latency_ms
                FROM traces
                WHERE estimated_cost_usd IS NOT NULL
                ORDER BY estimated_cost_usd DESC
                LIMIT 20
                """
            )

            expensive_rows = cursor.fetchall()

    return {
        "overview": {
            "total_requests": overall[0],
            "average_latency_ms": float(
                overall[1]
            ),
            "total_cost_usd": float(
                overall[2]
            ),
            "total_input_tokens": overall[3],
            "total_output_tokens": overall[4],
            "successful_requests": overall[5],
            "error_requests": overall[6],
            "blocked_requests": overall[7],
        },

        "models": [
            {
                "provider": row[0],
                "model": row[1],
                "requests": row[2],
                "average_latency_ms": float(
                    row[3]
                ),
                "total_cost_usd": float(
                    row[4]
                ),
                "input_tokens": row[5],
                "output_tokens": row[6],
            }
            for row in model_rows
        ],

        "spans": [
            {
                "span_type": row[0],
                "count": row[1],
                "average_duration_ms": float(
                    row[2]
                ),
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
                "provider": row[1],
                "model": row[2],
                "estimated_cost_usd": float(
                    row[3]
                ),
                "input_tokens": row[4],
                "output_tokens": row[5],
                "latency_ms": row[6],
            }
            for row in expensive_rows
        ],
    }


# ============================================================
# WORKFLOW BOTTLENECK / CRITICAL PATH
# ============================================================


@app.get("/traces/{trace_id}/analysis")
def analyze_trace(trace_id: str):
    validate_uuid(
        trace_id,
        "trace ID",
    )

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

    memo = {}

    def calculate_path(span_id):
        if span_id in memo:
            return memo[span_id]

        span = spans[span_id]

        duration = span["duration_ms"] or 0

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

    best_path = None

    for root_id in roots:
        result = calculate_path(root_id)

        if (
            best_path is None
            or result["duration_ms"]
            > best_path["duration_ms"]
        ):
            best_path = result

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

    total_span_duration_ms = sum(
        span["duration_ms"] or 0
        for span in spans.values()
    )

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

    bottlenecks.sort(
        key=lambda item: (
            item["duration_ms"] or 0
        ),
        reverse=True,
    )

    return {
        "trace_id": trace_id,
        "workflow_latency_ms": trace_row[1],
        "workflow_status": trace_row[2],

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
    validate_uuid(
        trace_id,
        "trace ID",
    )

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

            # Shadow traces are children of the
            # workflow trace.
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

    shadow_evaluations = []

    for row in shadow_rows:
        shadow_evaluations.append(
            {
                "trace_id": str(row[0]),
                "provider": row[1],
                "model": row[2],
                "input": row[3],
                "has_output": bool(
                    row[4]
                ),
                "context": row[5],
                "input_tokens": row[6],
                "output_tokens": row[7],
                "latency_ms": row[8],
                "estimated_cost_usd": (
                    float(row[9])
                    if row[9] is not None
                    else None
                ),
                "status": row[10],
                "factuality_score": (
                    float(row[11])
                    if row[11] is not None
                    else None
                ),
                "factuality_status": row[12],
                "evaluated_at": row[13],
            }
        )

    evaluated_shadow = [
        item
        for item in shadow_evaluations
        if item["factuality_status"]
        is not None
    ]

    scored_shadow = [
        item
        for item in evaluated_shadow
        if item["factuality_score"]
        is not None
    ]

    shadow_summary = {
        "evaluations": len(
            shadow_evaluations
        ),
        "evaluated": len(
            evaluated_shadow
        ),
        "average_factuality_score": (
            round(
                sum(
                    item["factuality_score"]
                    for item in scored_shadow
                )
                / len(scored_shadow),
                3,
            )
            if scored_shadow
            else None
        ),
        "supported": 0,
        "partially_supported": 0,
        "unsupported": 0,
        "pending": (
            len(shadow_evaluations)
            - len(evaluated_shadow)
        ),
    }

    for item in evaluated_shadow:
        status = item[
            "factuality_status"
        ]

        if status == "supported":
            shadow_summary[
                "supported"
            ] += 1

        elif status == "partially_supported":
            shadow_summary[
                "partially_supported"
            ] += 1

        elif status == "unsupported":
            shadow_summary[
                "unsupported"
            ] += 1

    # ---------------------------------------------------------
    # No spans
    # ---------------------------------------------------------

    if not span_rows:
        recommendations = []

        if shadow_summary[
            "unsupported"
        ] > 0:
            recommendations.append(
                "Shadow evaluation found an unsupported "
                "response. Improve grounding or retrieval."
            )

        elif shadow_summary[
            "partially_supported"
        ] > 0:
            recommendations.append(
                "Shadow evaluation found a partially "
                "supported response. Improve grounding "
                "or provide more relevant context."
            )

        if shadow_summary["pending"] > 0:
            recommendations.append(
                "Shadow evaluation is still pending."
            )

        return {
            "trace_id": trace_id,
            "summary": (
                "No spans were recorded "
                "for this trace."
            ),
            "performance": {
                "workflow_latency_ms": trace_row[3],
                "cost_usd": (
                    float(trace_row[4])
                    if trace_row[4] is not None
                    else None
                ),
                "bottleneck": None,
            },
            "shadow": shadow_summary,
            "shadow_evaluations": shadow_evaluations,
            "recommendations": recommendations,
            "performance_recommendations": [],
            "quality_recommendations": recommendations,
        }

    # ---------------------------------------------------------
    # Bottleneck
    # ---------------------------------------------------------

    bottleneck = span_rows[0]

    bottleneck_id = str(
        bottleneck[0]
    )
    bottleneck_name = bottleneck[1]
    bottleneck_type = bottleneck[2]
    bottleneck_duration = (
        bottleneck[3] or 0
    )

    total_span_duration = sum(
        (row[3] or 0)
        for row in span_rows
    )

    latency_share = 0.0

    if total_span_duration > 0:
        latency_share = (
            bottleneck_duration
            / total_span_duration
        ) * 100

    # ---------------------------------------------------------
    # Performance recommendations
    # ---------------------------------------------------------

    performance_recommendations = []

    if bottleneck_type == "llm":
        performance_recommendations.extend(
            [
                "Consider reducing prompt size "
                "or unnecessary context.",
                "Consider using a faster model "
                "when response quality permits.",
                "Consider caching reusable context "
                "or repeated requests.",
            ]
        )

    elif bottleneck_type == "retrieval":
        performance_recommendations.extend(
            [
                "Consider optimizing retrieval latency.",
                "Consider caching frequently requested data.",
                "Consider reducing the amount of retrieved data.",
            ]
        )

    elif bottleneck_type == "database":
        performance_recommendations.extend(
            [
                "Consider optimizing the database query.",
                "Check indexes and query execution time.",
                "Consider caching frequently accessed records.",
            ]
        )

    elif bottleneck_type == "agent":
        performance_recommendations.extend(
            [
                "Break the agent workflow into smaller spans.",
                "Inspect child spans to identify the "
                "underlying bottleneck.",
            ]
        )

    else:
        performance_recommendations.append(
            "Inspect this span and its children for "
            "latency optimization opportunities."
        )

    if bottleneck[4] == "error":
        performance_recommendations.insert(
            0,
            "This bottleneck ended with an error. "
            "Investigate the failing operation first.",
        )

    # ---------------------------------------------------------
    # Quality recommendations
    # ---------------------------------------------------------

    quality_recommendations = []

    if shadow_summary[
        "unsupported"
    ] > 0:
        quality_recommendations.append(
            "Shadow evaluation found an unsupported "
            "response. Improve grounding, retrieval "
            "quality, or context coverage."
        )

    if shadow_summary[
        "partially_supported"
    ] > 0:
        quality_recommendations.append(
            "Shadow evaluation found a partially "
            "supported response. Improve grounding "
            "or provide more relevant supporting context."
        )

    if (
        shadow_summary["supported"] > 0
        and not quality_recommendations
    ):
        quality_recommendations.append(
            "Shadow evaluation found the response "
            "supported by the provided context."
        )

    if shadow_summary["pending"] > 0:
        quality_recommendations.append(
            "One or more Shadow evaluations are still pending."
        )

    recommendations = (
        performance_recommendations
        + quality_recommendations
    )

    summary = (
        f"{bottleneck_name} is the primary latency "
        f"bottleneck, accounting for "
        f"{latency_share:.1f}% of recorded span time."
    )

    if (
        shadow_summary[
            "average_factuality_score"
        ]
        is not None
    ):
        summary += (
            " Shadow factuality score: "
            f"{shadow_summary['average_factuality_score']:.2f}."
        )

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

        "shadow_evaluations": (
            shadow_evaluations
        ),

        "recommendations": recommendations,

        "performance_recommendations": (
            performance_recommendations
        ),

        "quality_recommendations": (
            quality_recommendations
        ),
    }


# ============================================================
# SESSION ANALYTICS
# ============================================================


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*),

                    COALESCE(
                        AVG(latency_ms),
                        0
                    ),

                    COALESCE(
                        SUM(estimated_cost_usd),
                        0
                    ),

                    COALESCE(
                        SUM(input_tokens),
                        0
                    ),

                    COALESCE(
                        SUM(output_tokens),
                        0
                    ),

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

            if overview[0] == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found.",
                )

            cursor.execute(
                f"""
                SELECT
                    {TRACE_COLUMNS}
                FROM traces
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            )

            trace_rows = cursor.fetchall()

    workflows = [
        trace_to_dict(row)
        for row in trace_rows
    ]

    slowest = max(
        workflows,
        key=lambda item: (
            item["latency_ms"] or 0
        ),
    )

    costed = [
        item
        for item in workflows
        if item["estimated_cost_usd"]
        is not None
    ]

    most_expensive = (
        max(
            costed,
            key=lambda item: (
                item["estimated_cost_usd"]
                or 0
            ),
        )
        if costed
        else None
    )

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