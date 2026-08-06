-- =============================================================================
-- Migration: dual analyst assignment for water samples (chemical + micro)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_water_micro_analyst.sql
-- =============================================================================

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS assigned_micro_analyst_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_request_samples_assigned_micro_analyst
    ON request_samples (assigned_micro_analyst_id, status, expires_at);
