-- ==============================================================================
-- V7__create_cusum_state_and_flags.sql
-- Sprint 3 / Phase 3.4: Real-Time CUSUM Drift Detector State & System Flags
-- ==============================================================================

CREATE TABLE IF NOT EXISTS calibration_cusum_checkpoints (
    subsystem           VARCHAR(20) NOT NULL,
    criterion           VARCHAR(40) NOT NULL,
    c_plus              NUMERIC(8,4) NOT NULL DEFAULT 0.0,
    c_minus             NUMERIC(8,4) NOT NULL DEFAULT 0.0,
    sample_count        BIGINT NOT NULL DEFAULT 0,
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reset_at       TIMESTAMPTZ,
    PRIMARY KEY (subsystem, criterion)
);

CREATE TABLE IF NOT EXISTS calibration_system_flags (
    flag_key            VARCHAR(100) PRIMARY KEY,
    flag_value          BOOLEAN NOT NULL DEFAULT FALSE,
    reason              TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
