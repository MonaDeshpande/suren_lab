-- =============================================================================
-- Migration: Admin-defined custom formulas (category + package type scoped)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_custom_formulas.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS custom_formulas (
    id                  SERIAL PRIMARY KEY,
    test_key            TEXT        NOT NULL UNIQUE,
    name                TEXT        NOT NULL,
    method              TEXT        NOT NULL DEFAULT '',
    unit                TEXT        NOT NULL DEFAULT '',
    category            TEXT        NOT NULL
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer')),
    package_type        TEXT
                        CHECK (
                            package_type IS NULL
                            OR package_type IN (
                                'fssai', 'nutrition_only', 'detailed_nutrition'
                            )
                        ),
    formula_display     TEXT        NOT NULL,
    expression          TEXT        NOT NULL,
    use_dry_basis       BOOLEAN     NOT NULL DEFAULT FALSE,
    moisture_input_key  TEXT,
    protocol_family     TEXT        NOT NULL DEFAULT 'jaggery'
                        CHECK (protocol_family IN ('jaggery', 'nutrition')),
    current_version_no  INTEGER     NOT NULL DEFAULT 1
                        CHECK (current_version_no >= 1),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_custom_formulas_scope
    ON custom_formulas (category, package_type, is_active);

CREATE INDEX IF NOT EXISTS idx_custom_formulas_active
    ON custom_formulas (is_active, category);

CREATE TABLE IF NOT EXISTS custom_formula_inputs (
    id              SERIAL PRIMARY KEY,
    formula_id      INTEGER     NOT NULL
                    REFERENCES custom_formulas(id) ON DELETE CASCADE,
    field_key       TEXT        NOT NULL,
    label           TEXT        NOT NULL,
    unit            TEXT        NOT NULL DEFAULT '',
    required        BOOLEAN     NOT NULL DEFAULT TRUE,
    field_type      TEXT        NOT NULL DEFAULT 'number'
                    CHECK (field_type IN ('number', 'text', 'choice')),
    choices_json    TEXT        NOT NULL DEFAULT '[]',
    sort_order      INTEGER     NOT NULL DEFAULT 0,
    UNIQUE (formula_id, field_key)
);

CREATE INDEX IF NOT EXISTS idx_custom_formula_inputs_order
    ON custom_formula_inputs (formula_id, sort_order);
