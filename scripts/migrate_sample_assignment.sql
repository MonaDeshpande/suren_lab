-- =============================================================================
-- Migration: per-sample analyst assignment at Reception
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_sample_assignment.sql
-- =============================================================================

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS assigned_analyst_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_request_samples_assigned_analyst
    ON request_samples (assigned_analyst_id, status, expires_at);
