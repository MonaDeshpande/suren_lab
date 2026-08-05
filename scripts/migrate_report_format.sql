-- =============================================================================
-- Migration: per-sample final report format (with logo / without / both)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_report_format.sql
-- =============================================================================

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS report_format TEXT NOT NULL DEFAULT 'with_logo',
    ADD COLUMN IF NOT EXISTS tests_with_logo_json TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'request_samples_report_format_check'
    ) THEN
        ALTER TABLE request_samples
            ADD CONSTRAINT request_samples_report_format_check
            CHECK (report_format IN ('with_logo', 'without_logo', 'both'));
    END IF;
END $$;

UPDATE request_samples
   SET report_format = 'with_logo'
 WHERE report_format IS NULL;
