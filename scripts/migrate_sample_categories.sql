-- Migration: admin-defined sample categories (e.g. pharma) + relax category CHECKs
-- Safe to re-run.
--   docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_sample_categories.sql

CREATE TABLE IF NOT EXISTS sample_categories (
    category_key  TEXT        PRIMARY KEY,
    label         TEXT        NOT NULL,
    is_builtin    BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    sort_order    INTEGER     NOT NULL DEFAULT 100,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO sample_categories (category_key, label, is_builtin, is_active, sort_order)
VALUES
    ('food', 'Food', TRUE, TRUE, 10),
    ('water', 'Water', TRUE, TRUE, 20),
    ('cattle_feed_fertilizer', 'Cattle Feed / Fertilizer', TRUE, TRUE, 30),
    ('micro', 'Micro', TRUE, TRUE, 40)
ON CONFLICT (category_key) DO NOTHING;

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.conname, c.conrelid::regclass AS tbl
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.contype = 'c'
          AND c.conrelid::regclass::text IN (
              'request_samples', 'sample_test_packages', 'custom_formulas'
          )
          AND a.attname = 'category'
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
    END LOOP;

    ALTER TABLE request_samples
        ADD CONSTRAINT request_samples_category_check
        CHECK (char_length(trim(category)) > 0);

    ALTER TABLE sample_test_packages
        ADD CONSTRAINT sample_test_packages_category_check
        CHECK (char_length(trim(category)) > 0);

    ALTER TABLE custom_formulas
        ADD CONSTRAINT custom_formulas_category_check
        CHECK (char_length(trim(category)) > 0);
END $$;
