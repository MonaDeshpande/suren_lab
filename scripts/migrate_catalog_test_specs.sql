-- Built-in test metadata: method of analysis, limits, default units (Admin-editable).
CREATE TABLE IF NOT EXISTS catalog_test_specs (
    test_key            TEXT PRIMARY KEY,
    category            TEXT        NOT NULL
                        CHECK (category IN ('food', 'water', 'micro', 'cattle_feed_fertilizer')),
    test_name           TEXT        NOT NULL,
    method_of_analysis  TEXT        NOT NULL DEFAULT '',
    limits_text         TEXT,
    limits_desirable    TEXT,
    limits_permissible  TEXT,
    default_unit        TEXT        NOT NULL DEFAULT '',
    unit_editable       BOOLEAN     NOT NULL DEFAULT FALSE,
    sort_order          INTEGER     NOT NULL DEFAULT 0,
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    current_version_no  INTEGER     NOT NULL DEFAULT 1
                        CHECK (current_version_no >= 1),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalog_test_specs_category
    ON catalog_test_specs (category, sort_order);

-- Existing volumes: add version column when missing.
ALTER TABLE catalog_test_specs
    ADD COLUMN IF NOT EXISTS current_version_no INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'catalog_test_specs_current_version_no_check'
    ) THEN
        ALTER TABLE catalog_test_specs
            ADD CONSTRAINT catalog_test_specs_current_version_no_check
            CHECK (current_version_no >= 1);
    END IF;
END $$;
