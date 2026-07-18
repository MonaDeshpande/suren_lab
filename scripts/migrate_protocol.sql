-- Migration: shared protocol tables + tests_json (safe to re-run)
ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS tests_json TEXT;

CREATE TABLE IF NOT EXISTS sample_protocols (
    id                  SERIAL PRIMARY KEY,
    sample_id           INTEGER     NOT NULL UNIQUE
                        REFERENCES request_samples(id) ON DELETE CASCADE,
    protocol_no         TEXT,
    issued_to           TEXT,
    issued_by           TEXT,
    sample_received_on  DATE,
    date_of_analysis    DATE,
    appearance_text     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sample_test_results (
    id                  SERIAL PRIMARY KEY,
    sample_id           INTEGER     NOT NULL
                        REFERENCES request_samples(id) ON DELETE CASCADE,
    test_key            TEXT        NOT NULL,
    test_name           TEXT        NOT NULL,
    method              TEXT,
    unit                TEXT,
    inputs_json         TEXT,
    result_value        TEXT,
    result_numeric      DOUBLE PRECISION,
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sample_id, test_key)
);

CREATE INDEX IF NOT EXISTS idx_sample_test_results_sample
    ON sample_test_results (sample_id);
