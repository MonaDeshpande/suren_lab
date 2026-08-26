-- Row-level soft delete: is_active on business tables + partial unique indexes.

-- ---------------------------------------------------------------------------
-- Add is_active columns
-- ---------------------------------------------------------------------------
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE customer_contacts
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE test_requests
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE sample_protocols
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE sample_test_results
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_customers_active
    ON customers (is_active);

CREATE INDEX IF NOT EXISTS idx_test_requests_active
    ON test_requests (is_active);

CREATE INDEX IF NOT EXISTS idx_request_samples_active
    ON request_samples (is_active);

-- ---------------------------------------------------------------------------
-- customers: partial unique on gst_number (one active row per GSTIN)
-- ---------------------------------------------------------------------------
ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_gst_number_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_gst_active
    ON customers (gst_number)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- custom_formulas: partial unique on test_key
-- ---------------------------------------------------------------------------
ALTER TABLE custom_formulas DROP CONSTRAINT IF EXISTS custom_formulas_test_key_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_formulas_test_key_active
    ON custom_formulas (test_key)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- request_samples: partial unique on sample_code
-- ---------------------------------------------------------------------------
ALTER TABLE request_samples DROP CONSTRAINT IF EXISTS request_samples_sample_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_request_samples_code_active
    ON request_samples (sample_code)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- sample_test_packages: partial unique on product name + type + category
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_sample_test_packages_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_sample_test_packages_unique_active
    ON sample_test_packages (
        lower(trim(sample_product_name)),
        package_type,
        category
    )
    WHERE is_active = TRUE;
