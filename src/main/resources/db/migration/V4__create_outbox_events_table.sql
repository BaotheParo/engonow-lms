-- ==============================================================================
-- V4__create_outbox_events_table.sql
-- Sprint 2 / Phase 1: Transactional Outbox Pattern for EDA Event Ingestion
-- ==============================================================================

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_type VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version VARCHAR(10) NOT NULL DEFAULT '1.0',
    trace_id VARCHAR(100),
    correlation_id VARCHAR(100),
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_events_status_created_at
    ON outbox_events (status, created_at);

CREATE INDEX idx_outbox_events_aggregate
    ON outbox_events (aggregate_type, aggregate_id);

CREATE INDEX idx_outbox_events_pending
    ON outbox_events (created_at)
    WHERE status = 'PENDING';
