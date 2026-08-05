-- =============================================================================
-- migrate_user_roles.sql
-- Multi-role support: user_roles junction table; migrate users.role then drop it.
-- Safe to re-run (IF NOT EXISTS / conditional column drop).
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_roles (
    user_id     INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role        TEXT        NOT NULL
                CHECK (role IN ('admin', 'reception', 'analyst', 'reviewer')),
    PRIMARY KEY (user_id, role)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_role
    ON user_roles (role);

-- Copy legacy single-role column into junction table, then remove column.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'users'
           AND column_name = 'role'
    ) THEN
        INSERT INTO user_roles (user_id, role)
        SELECT id, role
          FROM users
         WHERE role IS NOT NULL
        ON CONFLICT (user_id, role) DO NOTHING;

        DROP INDEX IF EXISTS idx_users_role;
        ALTER TABLE users DROP COLUMN role;
    END IF;
END $$;
