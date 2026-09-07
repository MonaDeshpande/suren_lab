-- =============================================================================
-- Migration: one active test package per product name (Food)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_dedupe_packages.sql
-- =============================================================================

-- Deactivate duplicate active packages — keep the highest id per product name.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY lower(trim(sample_product_name)), category
               ORDER BY id DESC
           ) AS rn
      FROM sample_test_packages
     WHERE is_active = TRUE
)
UPDATE sample_test_packages p
   SET is_active = FALSE,
       updated_at = NOW()
  FROM ranked r
 WHERE p.id = r.id
   AND r.rn > 1;

DROP INDEX IF EXISTS idx_sample_test_packages_unique;
DROP INDEX IF EXISTS idx_sample_test_packages_unique_active;

CREATE UNIQUE INDEX IF NOT EXISTS idx_sample_test_packages_unique_active
    ON sample_test_packages (
        lower(trim(sample_product_name)),
        category
    )
    WHERE is_active = TRUE;
