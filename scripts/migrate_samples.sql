-- =============================================================================
-- Migration: add analyst workflow columns to request_samples
-- Run against an existing Docker volume that already has the old schema:
--   docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_samples.sql
--   OR:  python scripts/init_db.py  (re-applies full schema only on fresh DB)
-- =============================================================================

-- Add columns if missing (safe to re-run)
ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS sample_code TEXT,
    ADD COLUMN IF NOT EXISTS tests_to_perform TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS analyst_remarks TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '10 days');

-- Backfill sample_code for any legacy rows that lack one
UPDATE request_samples
   SET sample_code = 'LEGACY-' || id::TEXT
 WHERE sample_code IS NULL OR TRIM(sample_code) = '';

-- Backfill tests from parameters when empty
UPDATE request_samples
   SET tests_to_perform = parameters
 WHERE tests_to_perform IS NULL AND parameters IS NOT NULL;

UPDATE request_samples
   SET status = 'pending'
 WHERE status IS NULL;

UPDATE request_samples
   SET created_at = NOW()
 WHERE created_at IS NULL;

UPDATE request_samples
   SET updated_at = NOW()
 WHERE updated_at IS NULL;

UPDATE request_samples
   SET expires_at = COALESCE(created_at, NOW()) + INTERVAL '10 days'
 WHERE expires_at IS NULL;

-- Enforce NOT NULL / defaults going forward
ALTER TABLE request_samples
    ALTER COLUMN sample_code SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN status SET DEFAULT 'pending',
    ALTER COLUMN created_at SET DEFAULT NOW(),
    ALTER COLUMN updated_at SET DEFAULT NOW(),
    ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '10 days');

-- Unique sample codes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'request_samples_sample_code_key'
    ) THEN
        ALTER TABLE request_samples ADD CONSTRAINT request_samples_sample_code_key UNIQUE (sample_code);
    END IF;
END $$;

-- Status check constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'request_samples_status_check'
    ) THEN
        ALTER TABLE request_samples
            ADD CONSTRAINT request_samples_status_check
            CHECK (status IN ('pending', 'in_progress', 'completed'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_request_samples_code
    ON request_samples (sample_code);

CREATE INDEX IF NOT EXISTS idx_request_samples_status
    ON request_samples (status);

CREATE INDEX IF NOT EXISTS idx_request_samples_expires
    ON request_samples (expires_at);
