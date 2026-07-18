-- Migration: sample category for Food / Water / Cattle Feed–Fertilizer
-- Safe to re-run.
--   docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_category.sql

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS category TEXT;

-- Existing rows default to food (current catalog)
UPDATE request_samples
   SET category = 'food'
 WHERE category IS NULL OR TRIM(category) = '';

ALTER TABLE request_samples
    ALTER COLUMN category SET DEFAULT 'food';

ALTER TABLE request_samples
    ALTER COLUMN category SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'request_samples_category_check'
    ) THEN
        ALTER TABLE request_samples
            ADD CONSTRAINT request_samples_category_check
            CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_request_samples_category
    ON request_samples (category);
