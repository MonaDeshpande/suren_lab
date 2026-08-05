-- =============================================================================
-- Migration: validation gate for custom formulas (6-trial wizard)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_custom_formula_validation.sql
-- =============================================================================

ALTER TABLE custom_formulas
    ADD COLUMN IF NOT EXISTS is_validated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS validation_trials_json TEXT NOT NULL DEFAULT '[]';

-- Existing live formulas remain available without re-validation
UPDATE custom_formulas
   SET is_validated = TRUE
 WHERE is_active = TRUE
   AND is_validated = FALSE;
