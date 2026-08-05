-- Migration: add Micro sample category
-- Safe to re-run.
--   docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_micro_category.sql

DO $$
DECLARE
    r RECORD;
BEGIN
    -- Drop any existing category CHECK constraints on these tables
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
        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro'));

    ALTER TABLE sample_test_packages
        ADD CONSTRAINT sample_test_packages_category_check
        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro'));

    ALTER TABLE custom_formulas
        ADD CONSTRAINT custom_formulas_category_check
        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro'));
END $$;
