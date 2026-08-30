from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import get_connection


app = FastAPI(
    title="ControlPlane.AI",
    version="2.0.0",
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
# SCHEMA
# ============================================================

@app.on_event("startup")
def startup():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id UUID PRIMARY KEY,
                    name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id UUID PRIMARY KEY,
                    application_id UUID NOT NULL
                        REFERENCES applications(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    latency_ms INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    input TEXT,
                    output TEXT,
                    context TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    id UUID PRIMARY KEY,
                    run_id UUID NOT NULL
                        REFERENCES runs(id) ON DELETE CASCADE,
                    parent_trace_id UUID
                        REFERENCES traces(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input TEXT NOT NULL,
                    output TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    latency_ms INTEGER,
                    estimated_cost_usd DOUBLE PRECISION,
                    context TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    safety_flag BOOLEAN NOT NULL DEFAULT FALSE,
                    safety_type TEXT,
                    safety_action TEXT,
                    started_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    id UUID PRIMARY KEY,
                    trace_id UUID NOT NULL
                        REFERENCES traces(id) ON DELETE CASCADE,
                    parent_span_id UUID
                        REFERENCES spans(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    span_type TEXT NOT NULL,
                    input JSONB,
                    context JSONB,
                    output JSONB,
                    duration_ms INTEGER,
                    status TEXT NOT NULL DEFAULT 'success',
                    metadata JSONB,
                    started_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_application
                ON runs(application_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_traces_run
                ON traces(run_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spans_trace
                ON spans(trace_id)
            """)


# ============================================================
# MODELS
# ============================================================

class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    session_id: str = Field(min_length=1, max_length=255)


class RunCreate(BaseModel):
    input: str | None = None
    context: str | None = None


class RunUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    status: str | None = None
    output: str | None = None


class TraceCreate(BaseModel):
    provider: str
    model: str
    input: str
    output: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    context: str | None = None
    status: str = "pending"
    safety_flag: bool = False
    safety_type: str | None = None
    safety_action: str | None = None
    parent_trace_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class SpanCreate(BaseModel):
    name: str
    span_type: str
    input: Any | None = None
    context: Any | None = None
    output: Any | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    status: str = "success"
    metadata: dict[str, Any] | None = None
    parent_span_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


# ============================================================
# HELPERS
# ============================================================

def uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}. Expected a UUID.",
        )


def require_application(cursor, application_id: UUID):
    cursor.execute(
        """
        SELECT id, name, session_id, created_at
        FROM applications
        WHERE id = %s
        """,
        (application_id,),
    )
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found.",
        )

    return row


def require_run(cursor, run_id: UUID):
    cursor.execute(
        """
        SELECT
            id,
            application_id,
            created_at,
            started_at,
            ended_at,
            latency_ms,
            status,
            input,
            output,
            context
        FROM runs
        WHERE id = %s
        """,
        (run_id,),
    )
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    return row


def run_dict(row):
    return {
        "id": str(row[0]),
        "run_id": str(row[0]),
        "application_id": str(row[1]),
        "created_at": row[2],
        "started_at": row[3],
        "ended_at": row[4],
        "latency_ms": row[5],
        "status": row[6],
        "input": row[7],
        "output": row[8],
        "context": row[9],
    }


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
# APPLICATIONS
# ============================================================

@app.post("/applications")
def create_application(payload: ApplicationCreate):
    name = payload.name.strip()
    session_id = payload.session_id.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Application name is required.",
        )

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Project/session ID is required.",
        )

    application_id = uuid4()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO applications (
                    id,
                    name,
                    session_id
                )
                VALUES (%s, %s, %s)
                """,
                (application_id, name, session_id),
            )

    return {
        "id": str(application_id),
        "application_id": str(application_id),
        "name": name,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
    }


@app.get("/applications")
def list_applications(
    session_id: str | None = None,
):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if session_id:
                cursor.execute(
                    """
                    SELECT
                        a.id,
                        a.name,
                        a.session_id,
                        a.created_at,
                        COUNT(r.id)
                    FROM applications a
                    LEFT JOIN runs r
                        ON r.application_id = a.id
                    WHERE a.session_id = %s
                    GROUP BY
                        a.id,
                        a.name,
                        a.session_id,
                        a.created_at
                    ORDER BY a.created_at DESC
                    """,
                    (session_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        a.id,
                        a.name,
                        a.session_id,
                        a.created_at,
                        COUNT(r.id)
                    FROM applications a
                    LEFT JOIN runs r
                        ON r.application_id = a.id
                    GROUP BY
                        a.id,
                        a.name,
                        a.session_id,
                        a.created_at
                    ORDER BY a.created_at DESC
                    """
                )

            rows = cursor.fetchall()

    return [
        {
            "id": str(row[0]),
            "application_id": str(row[0]),
            "name": row[1],
            "session_id": row[2],
            "created_at": row[3],
            "run_count": row[4],
        }
        for row in rows
    ]


@app.get("/applications/{application_id}")
def get_application(application_id: str):
    app_id = uuid(application_id, "application ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            row = require_application(cursor, app_id)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM runs
                WHERE application_id = %s
                """,
                (app_id,),
            )
            run_count = cursor.fetchone()[0]

    return {
        "id": str(row[0]),
        "application_id": str(row[0]),
        "name": row[1],
        "session_id": row[2],
        "created_at": row[3],
        "run_count": run_count,
    }


# ============================================================
# RUNS
# ============================================================

@app.post("/applications/{application_id}/runs")
def create_run(
    application_id: str,
    payload: RunCreate,
):
    app_id = uuid(application_id, "application ID")
    run_id = uuid4()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            application = require_application(cursor, app_id)

            cursor.execute(
                """
                INSERT INTO runs (
                    id,
                    application_id,
                    input,
                    context,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    'pending'
                )
                """,
                (
                    run_id,
                    app_id,
                    payload.input,
                    payload.context,
                ),
            )

    return {
        "id": str(run_id),
        "run_id": str(run_id),
        "application_id": str(app_id),
        "application_name": application[1],
        "session_id": application[2],
        "status": "pending",
    }


@app.get("/applications/{application_id}/runs")
def list_runs(
    application_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    app_id = uuid(application_id, "application ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_application(cursor, app_id)

            cursor.execute(
                """
                SELECT
                    id,
                    application_id,
                    created_at,
                    started_at,
                    ended_at,
                    latency_ms,
                    status,
                    input,
                    output,
                    context
                FROM runs
                WHERE application_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (app_id, limit, offset),
            )

            rows = cursor.fetchall()

    return [run_dict(row) for row in rows]


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run_uuid = uuid(run_id, "run ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            row = require_run(cursor, run_uuid)

    return run_dict(row)


@app.patch("/runs/{run_id}")
def update_run(
    run_id: str,
    payload: RunUpdate,
):
    run_uuid = uuid(run_id, "run ID")

    updates = []
    values = []

    if payload.started_at is not None:
        updates.append("started_at = %s")
        values.append(payload.started_at)

    if payload.ended_at is not None:
        updates.append("ended_at = %s")
        values.append(payload.ended_at)

    if payload.latency_ms is not None:
        updates.append("latency_ms = %s")
        values.append(payload.latency_ms)

    if payload.status is not None:
        allowed = {
            "pending",
            "running",
            "success",
            "error",
            "blocked",
        }
        if payload.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail="Invalid run status.",
            )

        updates.append("status = %s")
        values.append(payload.status)

    if payload.output is not None:
        updates.append("output = %s")
        values.append(payload.output)

    if not updates:
        return {
            "run_id": str(run_uuid),
            "status": "unchanged",
        }

    values.append(run_uuid)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_run(cursor, run_uuid)

            cursor.execute(
                f"""
                UPDATE runs
                SET {", ".join(updates)}
                WHERE id = %s
                """,
                tuple(values),
            )

            # A run owns its traces. Keep the root trace lifecycle
            # synchronized with the run lifecycle so application code
            # never needs to manage trace lifecycle explicitly.
            trace_updates = []
            trace_values = []

            if payload.started_at is not None:
                trace_updates.append("started_at = %s")
                trace_values.append(payload.started_at)

            if payload.ended_at is not None:
                trace_updates.append("ended_at = %s")
                trace_values.append(payload.ended_at)

            if payload.latency_ms is not None:
                trace_updates.append("latency_ms = %s")
                trace_values.append(payload.latency_ms)

            if payload.status is not None:
                trace_updates.append("status = %s")
                trace_values.append(payload.status)

            if payload.output is not None:
                trace_updates.append("output = %s")
                trace_values.append(payload.output)

            if trace_updates:
                trace_values.append(run_uuid)

                cursor.execute(
                    f"""
                    UPDATE traces
                    SET {", ".join(trace_updates)}
                    WHERE run_id = %s
                      AND parent_trace_id IS NULL
                    """,
                    tuple(trace_values),
                )

    return {
        "run_id": str(run_uuid),
        "status": "updated",
    }


# ============================================================
# CHILD TRACES
# ============================================================

@app.post("/runs/{run_id}/traces")
def create_trace(
    run_id: str,
    payload: TraceCreate,
):
    """
    Create a trace inside an existing run.

    The trace ID is generated by ControlPlane.
    The caller cannot supply a root/run ID.
    """

    run_uuid = uuid(run_id, "run ID")
    trace_id = uuid4()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_run(cursor, run_uuid)

            parent_trace_id = None

            if payload.parent_trace_id:
                parent_trace_id = uuid(
                    payload.parent_trace_id,
                    "parent trace ID",
                )

                cursor.execute(
                    """
                    SELECT run_id
                    FROM traces
                    WHERE id = %s
                    """,
                    (parent_trace_id,),
                )

                parent = cursor.fetchone()

                if parent is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Parent trace not found.",
                    )

                if parent[0] != run_uuid:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Parent trace belongs to a different run."
                        ),
                    )

            cursor.execute(
                """
                INSERT INTO traces (
                    id,
                    run_id,
                    parent_trace_id,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    started_at,
                    ended_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    trace_id,
                    run_uuid,
                    parent_trace_id,
                    payload.provider,
                    payload.model,
                    payload.input,
                    payload.output,
                    payload.input_tokens,
                    payload.output_tokens,
                    payload.latency_ms,
                    payload.estimated_cost_usd,
                    payload.context,
                    payload.status,
                    payload.safety_flag,
                    payload.safety_type,
                    payload.safety_action,
                    payload.started_at,
                    payload.ended_at,
                ),
            )

    return {
        "id": str(trace_id),
        "trace_id": str(trace_id),
        "run_id": str(run_uuid),
        "status": "created",
    }


@app.get("/runs/{run_id}/traces")
def list_run_traces(
    run_id: str,
    limit: int = Query(500, ge=1, le=2000),
):
    run_uuid = uuid(run_id, "run ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            require_run(cursor, run_uuid)

            cursor.execute(
                """
                SELECT
                    id,
                    parent_trace_id,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    started_at,
                    ended_at,
                    created_at
                FROM traces
                WHERE run_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (run_uuid, limit),
            )

            rows = cursor.fetchall()

    return [
        {
            "id": str(row[0]),
            "trace_id": str(row[0]),
            "run_id": str(run_uuid),
            "parent_trace_id": (
                str(row[1]) if row[1] else None
            ),
            "provider": row[2],
            "model": row[3],
            "input": row[4],
            "output": row[5],
            "input_tokens": row[6],
            "output_tokens": row[7],
            "latency_ms": row[8],
            "estimated_cost_usd": row[9],
            "context": row[10],
            "status": row[11],
            "safety_flag": row[12],
            "safety_type": row[13],
            "safety_action": row[14],
            "started_at": row[15],
            "ended_at": row[16],
            "created_at": row[17],
        }
        for row in rows
    ]


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    trace_uuid = uuid(trace_id, "trace ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    run_id,
                    parent_trace_id,
                    provider,
                    model,
                    input,
                    output,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    estimated_cost_usd,
                    context,
                    status,
                    safety_flag,
                    safety_type,
                    safety_action,
                    started_at,
                    ended_at,
                    created_at
                FROM traces
                WHERE id = %s
                """,
                (trace_uuid,),
            )

            row = cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Trace not found.",
        )

    return {
        "id": str(row[0]),
        "trace_id": str(row[0]),
        "run_id": str(row[1]),
        "parent_trace_id": str(row[2]) if row[2] else None,
        "provider": row[3],
        "model": row[4],
        "input": row[5],
        "output": row[6],
        "input_tokens": row[7],
        "output_tokens": row[8],
        "latency_ms": row[9],
        "estimated_cost_usd": row[10],
        "context": row[11],
        "status": row[12],
        "safety_flag": row[13],
        "safety_type": row[14],
        "safety_action": row[15],
        "started_at": row[16],
        "ended_at": row[17],
        "created_at": row[18],
    }


# ============================================================
# TRACE INSIGHTS
# ============================================================

@app.get("/traces/{trace_id}/insights")
def get_trace_insights(trace_id: str):
    trace_uuid = uuid(trace_id, "trace ID")

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
                (trace_uuid,),
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
                (trace_uuid,),
            )

            span_rows = cursor.fetchall()

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
                    status
                FROM traces
                WHERE parent_trace_id = %s
                ORDER BY created_at DESC
                """,
                (trace_uuid,),
            )

            child_rows = cursor.fetchall()

    shadow_evaluations = []

    for row in child_rows:
        shadow_evaluations.append(
            {
                "trace_id": str(row[0]),
                "provider": row[1],
                "model": row[2],
                "input": row[3],
                "output": row[4],
                "context": row[5],
                "input_tokens": row[6],
                "output_tokens": row[7],
                "latency_ms": row[8],
                "estimated_cost_usd": (
                    float(row[9]) if row[9] is not None else None
                ),
                "status": row[10],
                "factuality_score": None,
                "factuality_status": None,
                "evaluated_at": None,
            }
        )

    evaluated = [
        item for item in shadow_evaluations
        if item["factuality_status"] is not None
    ]

    scored = [
        item for item in evaluated
        if item["factuality_score"] is not None
    ]

    supported = sum(
        item["factuality_status"] == "supported"
        for item in evaluated
    )
    partially_supported = sum(
        item["factuality_status"] == "partially_supported"
        for item in evaluated
    )
    unsupported = sum(
        item["factuality_status"] == "unsupported"
        for item in evaluated
    )

    pending = len(shadow_evaluations) - len(evaluated)

    average_score = (
        round(
            sum(item["factuality_score"] for item in scored)
            / len(scored),
            3,
        )
        if scored
        else None
    )

    bottleneck = None

    if span_rows:
        row = span_rows[0]
        total_duration = sum(
            (item[3] or 0) for item in span_rows
        )

        bottleneck = {
            "span_id": str(row[0]),
            "name": row[1],
            "span_type": row[2],
            "duration_ms": row[3] or 0,
            "latency_share": round(
                ((row[3] or 0) / total_duration * 100)
                if total_duration
                else 0,
                2,
            ),
            "status": row[4],
        }

    performance_recommendations = []

    if bottleneck:
        if bottleneck["span_type"] == "llm":
            performance_recommendations.extend(
                [
                    "Consider reducing prompt size or unnecessary context.",
                    "Consider using a faster model when response quality permits.",
                    "Consider caching reusable context or repeated requests.",
                ]
            )
        else:
            performance_recommendations.append(
                "Inspect the slowest span for latency optimization opportunities."
            )

    quality_recommendations = []

    if unsupported:
        quality_recommendations.append(
            "Shadow evaluation found an unsupported response."
        )

    if partially_supported:
        quality_recommendations.append(
            "Shadow evaluation found a partially supported response."
        )

    if supported and not quality_recommendations:
        quality_recommendations.append(
            "Shadow evaluation found the response supported by the provided context."
        )

    if pending:
        quality_recommendations.append(
            "Shadow evaluation is pending."
        )

    return {
        "trace_id": str(trace_uuid),
        "summary": (
            "Workflow completed successfully."
            if trace_row[5] == "success"
            else f"Workflow status: {trace_row[5]}."
        ),
        "performance": {
            "workflow_latency_ms": trace_row[3],
            "cost_usd": (
                float(trace_row[4])
                if trace_row[4] is not None
                else None
            ),
            "bottleneck": bottleneck,
        },
        "shadow": {
            "evaluations": len(shadow_evaluations),
            "evaluated": len(evaluated),
            "average_factuality_score": average_score,
            "supported": supported,
            "partially_supported": partially_supported,
            "unsupported": unsupported,
            "pending": pending,
        },
        "shadow_evaluations": shadow_evaluations,
        "recommendations": (
            performance_recommendations
            + quality_recommendations
        ),
        "performance_recommendations": performance_recommendations,
        "quality_recommendations": quality_recommendations,
    }


# ============================================================
# SPANS
# ============================================================

@app.post("/traces/{trace_id}/spans")
def create_span(
    trace_id: str,
    payload: SpanCreate,
):
    trace_uuid = uuid(trace_id, "trace ID")
    span_id = uuid4()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM traces
                WHERE id = %s
                """,
                (trace_uuid,),
            )

            trace = cursor.fetchone()

            if trace is None:
                raise HTTPException(
                    status_code=404,
                    detail="Trace not found.",
                )

            parent_span_id = None

            if payload.parent_span_id:
                parent_span_id = uuid(
                    payload.parent_span_id,
                    "parent span ID",
                )

                cursor.execute(
                    """
                    SELECT trace_id
                    FROM spans
                    WHERE id = %s
                    """,
                    (parent_span_id,),
                )

                parent = cursor.fetchone()

                if parent is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Parent span not found.",
                    )

                if parent[0] != trace_uuid:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Parent span belongs to a different trace."
                        ),
                    )

            import json

            cursor.execute(
                """
                INSERT INTO spans (
                    id,
                    trace_id,
                    parent_span_id,
                    name,
                    span_type,
                    input,
                    context,
                    output,
                    duration_ms,
                    status,
                    metadata,
                    started_at,
                    ended_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    span_id,
                    trace_uuid,
                    parent_span_id,
                    payload.name,
                    payload.span_type,
                    json.dumps(payload.input),
                    json.dumps(payload.context),
                    json.dumps(payload.output),
                    payload.duration_ms,
                    payload.status,
                    json.dumps(payload.metadata or {}),
                    payload.started_at,
                    payload.ended_at,
                ),
            )

    return {
        "id": str(span_id),
        "span_id": str(span_id),
        "trace_id": str(trace_uuid),
        "status": "created",
    }


@app.get("/traces/{trace_id}/spans")
def list_spans(trace_id: str):
    trace_uuid = uuid(trace_id, "trace ID")

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
                    input,
                    context,
                    output,
                    duration_ms,
                    status,
                    metadata,
                    started_at,
                    ended_at,
                    created_at
                FROM spans
                WHERE trace_id = %s
                ORDER BY created_at ASC
                """,
                (trace_uuid,),
            )

            rows = cursor.fetchall()

    return [
        {
            "id": str(row[0]),
            "span_id": str(row[0]),
            "trace_id": str(row[1]),
            "parent_span_id": (
                str(row[2]) if row[2] else None
            ),
            "name": row[3],
            "span_type": row[4],
            "input": row[5],
            "context": row[6],
            "output": row[7],
            "duration_ms": row[8],
            "status": row[9],
            "metadata": row[10],
            "started_at": row[11],
            "ended_at": row[12],
            "created_at": row[13],
        }
        for row in rows
    ]
