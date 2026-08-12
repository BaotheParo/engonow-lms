-- Sprint 1: foundational persistence model for the AI Writing subsystem.
-- PostgreSQL 13+ exposes gen_random_uuid() as a built-in function.

CREATE TABLE writing_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL,
    task_type VARCHAR(20) NOT NULL
        CONSTRAINT ck_writing_submissions_task_type
            CHECK (task_type IN ('ACADEMIC_TASK1', 'GENERAL_TASK1', 'TASK2', 'FULL_TEST')),
    task_prompt TEXT NOT NULL,
    essay_text TEXT NOT NULL,
    word_count INTEGER NOT NULL
        CONSTRAINT ck_writing_submissions_word_count
            CHECK (word_count >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CONSTRAINT ck_writing_submissions_status
            CHECK (status IN ('PENDING', 'PROCESSING', 'SCORED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_writing_submissions_student_id
    ON writing_submissions (student_id);

CREATE INDEX idx_writing_submissions_status
    ON writing_submissions (status);

CREATE TABLE writing_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL
        CONSTRAINT fk_writing_results_submission
            REFERENCES writing_submissions (id) ON DELETE CASCADE,
    task_achievement_score NUMERIC(2, 1) NOT NULL
        CONSTRAINT ck_writing_results_task_achievement_score
            CHECK (task_achievement_score IN (
                0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5,
                5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9
            )),
    coherence_cohesion_score NUMERIC(2, 1) NOT NULL
        CONSTRAINT ck_writing_results_coherence_cohesion_score
            CHECK (coherence_cohesion_score IN (
                0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5,
                5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9
            )),
    lexical_resource_score NUMERIC(2, 1) NOT NULL
        CONSTRAINT ck_writing_results_lexical_resource_score
            CHECK (lexical_resource_score IN (
                0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5,
                5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9
            )),
    grammatical_range_score NUMERIC(2, 1) NOT NULL
        CONSTRAINT ck_writing_results_grammatical_range_score
            CHECK (grammatical_range_score IN (
                0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5,
                5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9
            )),
    overall_band NUMERIC(2, 1) NOT NULL
        CONSTRAINT ck_writing_results_overall_band
            CHECK (overall_band IN (
                0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5,
                5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9
            )),
    feedback_detail JSONB NOT NULL,
    ai_model_version VARCHAR(60) NOT NULL,
    evaluated_by VARCHAR(20) NOT NULL DEFAULT 'AI_AUTO'
        CONSTRAINT ck_writing_results_evaluated_by
            CHECK (evaluated_by IN ('AI_AUTO', 'HUMAN_OVERRIDE')),
    result_version INTEGER NOT NULL DEFAULT 1
        CONSTRAINT ck_writing_results_result_version
            CHECK (result_version >= 1),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    evaluated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0
);

-- PostgreSQL does not automatically index foreign-key columns. This complete
-- index accelerates ON DELETE CASCADE checks and scans across all historical
-- result versions belonging to a submission.
CREATE INDEX idx_writing_results_submission_id
    ON writing_results (submission_id);

-- This separate partial unique index enforces the domain invariant that a
-- submission has at most one current result. It cannot replace the complete
-- index above because it excludes superseded rows from its index entries.
CREATE UNIQUE INDEX ux_writing_results_current_per_submission
    ON writing_results (submission_id)
    WHERE is_current = TRUE;

-- Uses PostgreSQL's default jsonb_ops operator class, supporting containment
-- as well as key/key-path existence queries against the complete payload.
CREATE INDEX idx_writing_results_feedback_detail_gin
    ON writing_results USING GIN (feedback_detail);

CREATE INDEX idx_writing_results_overall_band
    ON writing_results (overall_band);
