-- =============================================================================
-- migrate_audit.sql
-- Central audit_log: who / when / action / entity for every meaningful write.
-- Safe to re-run (IF NOT EXISTS).
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name    TEXT NOT NULL,
    action       TEXT NOT NULL,
    entity_table TEXT NOT NULL,
    entity_id    TEXT,
    details      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at
    ON audit_log (occurred_at DESC);
