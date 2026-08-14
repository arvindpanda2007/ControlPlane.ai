CREATE TABLE IF NOT EXISTS traces (
    id UUID PRIMARY KEY,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,

    input TEXT NOT NULL,
    output TEXT,

    input_tokens INTEGER,
    output_tokens INTEGER,

    latency_ms INTEGER,
    estimated_cost_usd DOUBLE PRECISION,

    session_id VARCHAR(255),

    status VARCHAR(50) NOT NULL DEFAULT 'success',

    safety_flag BOOLEAN NOT NULL DEFAULT FALSE,
    safety_type VARCHAR(100),
    safety_action VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_traces_created_at
    ON traces (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_traces_session_id
    ON traces (session_id);

CREATE TABLE IF NOT EXISTS spans (
    id UUID PRIMARY KEY,

    trace_id UUID NOT NULL,

    parent_span_id UUID,

    name VARCHAR(255) NOT NULL,

    span_type VARCHAR(50) NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    ended_at TIMESTAMPTZ,

    duration_ms INTEGER,

    status VARCHAR(50) NOT NULL DEFAULT 'success',

    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id
    ON spans (trace_id);

CREATE INDEX IF NOT EXISTS idx_spans_parent_span_id
    ON spans (parent_span_id);

CREATE INDEX IF NOT EXISTS idx_spans_started_at
    ON spans (started_at DESC);