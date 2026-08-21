-- Create table for idempotent event processing (Inbox Pattern)
CREATE TABLE IF NOT EXISTS inbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL,
    idempotency_key UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    source_service VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
    retry_count INT NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ NULL
);

-- Ensure absolute idempotency at DB index layer
CREATE UNIQUE INDEX IF NOT EXISTS ux_inbox_idempotency_key ON inbox_events (idempotency_key);

-- Index for operational sweeps and health metrics
CREATE INDEX IF NOT EXISTS idx_inbox_status_received ON inbox_events (status, received_at);
