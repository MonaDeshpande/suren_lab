-- =============================================================================
-- migrate_versions.sql
-- entity_versions: immutable snapshots before each edit + edit_reason on audit_log.
-- Safe to re-run (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- =============================================================================

CREATE TABLE IF NOT EXISTS entity_versions (
    id              BIGSERIAL PRIMARY KEY,
    entity_table    TEXT        NOT NULL,
    entity_id       TEXT        NOT NULL,
    version_no      INTEGER     NOT NULL,
    snapshot_json   TEXT        NOT NULL,
    edit_reason     TEXT        NOT NULL,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name       TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_table, entity_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_entity_versions_entity
    ON entity_versions (entity_table, entity_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_entity_versions_created_at
    ON entity_versions (created_at DESC);

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS edit_reason TEXT;
