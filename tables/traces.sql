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