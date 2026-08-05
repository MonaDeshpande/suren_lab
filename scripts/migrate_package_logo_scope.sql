-- =============================================================================
-- Migration: dual with-logo / without-logo test sets on packages and samples
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_package_logo_scope.sql
-- =============================================================================

ALTER TABLE sample_test_package_tests
    ADD COLUMN IF NOT EXISTS logo_scope TEXT NOT NULL DEFAULT 'with_logo';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sample_test_package_tests_logo_scope_check'
    ) THEN
        ALTER TABLE sample_test_package_tests
            ADD CONSTRAINT sample_test_package_tests_logo_scope_check
            CHECK (logo_scope IN ('with_logo', 'without_logo'));
    END IF;
END $$;

UPDATE sample_test_package_tests
   SET logo_scope = 'with_logo'
 WHERE logo_scope IS NULL;

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS tests_without_logo_json TEXT;

-- Backfill without-logo keys for existing without_logo samples
UPDATE request_samples
   SET tests_without_logo_json = tests_json
 WHERE report_format = 'without_logo'
   AND tests_without_logo_json IS NULL
   AND tests_json IS NOT NULL
   AND trim(tests_json) <> '';

-- Backfill without-logo keys for both (complement of with-logo subset)
UPDATE request_samples rs
   SET tests_without_logo_json = sub.nwl_json
  FROM (
        SELECT rs2.id,
               (
                   SELECT json_agg(elem ORDER BY ord)
                     FROM (
                              SELECT elem, ord
                                FROM jsonb_array_elements_text(rs2.tests_json::jsonb)
                                     WITH ORDINALITY AS t(elem, ord)
                               WHERE elem NOT IN (
                                         SELECT jsonb_array_elements_text(
                                                    COALESCE(rs2.tests_with_logo_json, '[]')::jsonb
                                                )
                                     )
                          ) filtered
               ) AS nwl_json
          FROM request_samples rs2
         WHERE rs2.report_format = 'both'
           AND rs2.tests_without_logo_json IS NULL
           AND rs2.tests_json IS NOT NULL
           AND trim(rs2.tests_json) <> ''
       ) sub
 WHERE rs.id = sub.id
   AND sub.nwl_json IS NOT NULL;
