from fastapi import FastAPI
from pydantic import BaseModel
from psycopg.types.json import Jsonb
from .database import get_connection


app = FastAPI(title="ControlPlane.AI")


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
# TRACES
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
                    safety_action
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
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
                ),
            )

    return {
        "id": trace_id,
        "status": "created",
    }


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
            "factuality_score": row[16],
            "factuality_status": row[17],
            "evaluated_at": row[18],
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
# SPANS
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


@app.get("/spans/{trace_id}")
def get_spans(trace_id: str):

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
            "metadata": row[9],
        }
        for row in rows
    ]