-- =============================================================================
-- Migration: versioned test packages for Food samples (FSSAI / Nutrition / etc.)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_test_packages.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS sample_test_packages (
    id                  SERIAL PRIMARY KEY,
    sample_product_name TEXT        NOT NULL,
    package_type        TEXT        NOT NULL
                        CHECK (package_type IN (
                            'fssai', 'nutrition_only', 'detailed_nutrition'
                        )),
    category            TEXT        NOT NULL DEFAULT 'food'
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer')),
    current_version_no  INTEGER     NOT NULL DEFAULT 1
                        CHECK (current_version_no >= 1),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sample_test_packages_unique
    ON sample_test_packages (
        lower(trim(sample_product_name)),
        package_type,
        category
    );

CREATE INDEX IF NOT EXISTS idx_sample_test_packages_active
    ON sample_test_packages (is_active, lower(trim(sample_product_name)));

CREATE TABLE IF NOT EXISTS sample_test_package_tests (
    package_id  INTEGER NOT NULL
                REFERENCES sample_test_packages(id) ON DELETE CASCADE,
    test_key    TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (package_id, test_key)
);

CREATE INDEX IF NOT EXISTS idx_sample_test_package_tests_order
    ON sample_test_package_tests (package_id, sort_order);

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS package_id INTEGER
        REFERENCES sample_test_packages(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS package_version_no INTEGER,
    ADD COLUMN IF NOT EXISTS package_type TEXT
        CHECK (
            package_type IS NULL
            OR package_type IN ('fssai', 'nutrition_only', 'detailed_nutrition')
        );

CREATE INDEX IF NOT EXISTS idx_request_samples_package
    ON request_samples (package_id);
