-- ==============================================================================
-- V6__create_calibration_corpus_tables.sql
-- Sprint 3 / Phase 3.1: Golden Calibration Corpus Foundation & Intake Tooling
-- ==============================================================================

-- 1. Table: calibration_corpus_items
CREATE TABLE calibration_corpus_items (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subsystem                     VARCHAR(20) NOT NULL CHECK (subsystem IN ('WRITING', 'SPEAKING')),
    task_type                     VARCHAR(50) NOT NULL, -- WRITING: ACADEMIC_TASK1, GENERAL_TASK1, TASK2; SPEAKING: PART_1, PART_2, PART_3
    prompt_text                   TEXT NOT NULL,
    essay_text                    TEXT,
    source_audio_url              TEXT,
    source_audio_duration_seconds INT,
    source_transcript             TEXT,
    calibration_hold_until        TIMESTAMPTZ,
    target_band_stratum           VARCHAR(10) NOT NULL CHECK (target_band_stratum IN ('4.0-4.5','5.0-5.5','6.0-6.5','7.0-7.5','8.0-8.5')),
    dataset_split                 VARCHAR(20) NOT NULL DEFAULT 'UNASSIGNED' CHECK (dataset_split IN ('TUNING', 'GATEKEEPER', 'UNASSIGNED')),
    split_assigned_at             TIMESTAMPTZ,
    split_locked_at               TIMESTAMPTZ,
    intake_batch_id               UUID NOT NULL,
    content_hash                  VARCHAR(64),
    status                        VARCHAR(40) NOT NULL DEFAULT 'PENDING_RATING' 
                                  CHECK (status IN ('PENDING_RATING', 'RATING_IN_PROGRESS', 'DISCORDANT_PENDING_ADJUDICATION', 'ADJUDICATED', 'ACTIVE', 'RETIRED')),
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                       BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_writing_has_essay CHECK (subsystem <> 'WRITING' OR essay_text IS NOT NULL),
    CONSTRAINT chk_speaking_has_audio CHECK (subsystem <> 'SPEAKING' OR source_audio_url IS NOT NULL)
);

CREATE INDEX idx_calibration_items_split ON calibration_corpus_items (subsystem, dataset_split);
CREATE INDEX idx_calibration_items_stratum ON calibration_corpus_items (target_band_stratum);
CREATE INDEX idx_calibration_items_status ON calibration_corpus_items (status);
CREATE INDEX idx_calibration_items_batch ON calibration_corpus_items (intake_batch_id);
CREATE INDEX idx_calibration_items_dedup_lookup ON calibration_corpus_items (subsystem, task_type);
CREATE INDEX idx_calibration_items_content_hash ON calibration_corpus_items (content_hash);

-- Trigger: Immutability guard for dataset_split
CREATE OR REPLACE FUNCTION fn_prevent_split_change_after_lock() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.split_locked_at IS NOT NULL AND NEW.dataset_split IS DISTINCT FROM OLD.dataset_split THEN
        RAISE EXCEPTION 'dataset_split is locked for corpus item % (locked at %)', OLD.id, OLD.split_locked_at;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_split_change
    BEFORE UPDATE ON calibration_corpus_items
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_split_change_after_lock();

-- 2. Table: calibration_human_ratings
CREATE TABLE calibration_human_ratings (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    corpus_item_id                UUID NOT NULL REFERENCES calibration_corpus_items (id) ON DELETE CASCADE,
    rater_id                      UUID NOT NULL,
    rater_credential_level        VARCHAR(30) NOT NULL CHECK (rater_credential_level IN ('SENIOR_EXAMINER', 'CERTIFIED_EXAMINER', 'TRAINEE')),
    criterion                     VARCHAR(40) NOT NULL CHECK (criterion IN ('TASK_ACHIEVEMENT', 'TASK_RESPONSE', 'COHERENCE_COHESION', 'FLUENCY_COHERENCE', 'LEXICAL_RESOURCE', 'GRAMMATICAL_RANGE_ACCURACY', 'PRONUNCIATION', 'OVERALL')),
    band_score                    NUMERIC(2,1) NOT NULL CHECK (band_score IN (0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0,6.5,7.0,7.5,8.0,8.5,9.0)),
    transcript_flagged_incorrect  BOOLEAN NOT NULL DEFAULT FALSE,
    rating_notes                  TEXT,
    rated_at                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_rating_per_rater_criterion UNIQUE (corpus_item_id, rater_id, criterion)
);

CREATE INDEX idx_calibration_ratings_item ON calibration_human_ratings (corpus_item_id);

-- 3. Table: calibration_reference_scores
CREATE TABLE calibration_reference_scores (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    corpus_item_id                UUID NOT NULL REFERENCES calibration_corpus_items (id) ON DELETE CASCADE,
    criterion                     VARCHAR(40) NOT NULL CHECK (criterion IN ('TASK_ACHIEVEMENT', 'TASK_RESPONSE', 'COHERENCE_COHESION', 'FLUENCY_COHERENCE', 'LEXICAL_RESOURCE', 'GRAMMATICAL_RANGE_ACCURACY', 'PRONUNCIATION', 'OVERALL')),
    reference_band                NUMERIC(2,1) NOT NULL CHECK (reference_band IN (0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0,6.5,7.0,7.5,8.0,8.5,9.0)),
    resolution_method             VARCHAR(30) NOT NULL CHECK (resolution_method IN ('MEAN_OF_RATERS', 'ADJUDICATED', 'SINGLE_RATER_PROVISIONAL')),
    contributing_rating_ids       UUID[] NOT NULL,
    icc_at_resolution             NUMERIC(4,3),
    discordant                    BOOLEAN NOT NULL DEFAULT FALSE,
    adjudicator_id                UUID,
    resolved_at                   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reference_per_item_criterion UNIQUE (corpus_item_id, criterion)
);

CREATE INDEX idx_calibration_ref_scores_item ON calibration_reference_scores (corpus_item_id);
