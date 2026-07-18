-- =============================================================================
-- migrate_auth.sql
-- Add users table + extend sample status with 'reported' for reviewer handoff.
-- Safe to re-run (IF NOT EXISTS / DROP CONSTRAINT IF EXISTS).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT        NOT NULL UNIQUE,
    password_hash        TEXT        NOT NULL,
    full_name            TEXT,
    role                 TEXT        NOT NULL
                         CHECK (role IN ('admin', 'reception', 'analyst', 'reviewer')),
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username
    ON users (username);

CREATE INDEX IF NOT EXISTS idx_users_role
    ON users (role);

-- updated_at trigger (function may already exist from schema)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE PROCEDURE set_updated_at();

-- ---------------------------------------------------------------------------
-- request_samples.status — allow 'reported'
-- ---------------------------------------------------------------------------
ALTER TABLE request_samples
    DROP CONSTRAINT IF EXISTS request_samples_status_check;

ALTER TABLE request_samples
    ADD CONSTRAINT request_samples_status_check
    CHECK (status IN ('pending', 'in_progress', 'completed', 'reported'));
