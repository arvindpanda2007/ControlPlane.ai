from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from .database import get_connection


app = FastAPI(title="ControlPlane.AI")


class TraceCreate(BaseModel):
    provider: str
    model: str
    input: str
    output: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    session_id: str | None = None
    status: str = "success"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/traces")
def create_trace(trace: TraceCreate):
    trace_id = uuid4()

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
                    session_id,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    trace.session_id,
                    trace.status,
                ),
            )

    return {
        "id": str(trace_id),
        "status": "created",
    }