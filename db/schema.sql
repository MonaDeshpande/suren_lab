-- =============================================================================
-- SLS Food Testing Lab — Database Schema
-- Customer Test Request system
-- =============================================================================
-- Permanent customer master + per-request intake records.
-- GST number is the unique business key when provided (optional).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- customers  (PERMANENT master data)
-- ---------------------------------------------------------------------------
-- Holds identity details that are reused across many test requests.
-- Upserted by gst_number when a form is submitted.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              SERIAL PRIMARY KEY,
    customer_name   TEXT        NOT NULL,          -- Company / customer name
    address         TEXT,                          -- Full postal address
    contact_person  TEXT,                          -- Name of contact person
    contact_number  TEXT,                          -- Phone / mobile
    email           TEXT,                          -- Email ID
    gst_number      TEXT,                          -- GSTIN — unique when set (active rows)
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_gst_active
    ON customers (gst_number)
    WHERE is_active = TRUE AND gst_number IS NOT NULL;

-- Fast lookup by GST or partial name search
CREATE INDEX IF NOT EXISTS idx_customers_gst
    ON customers (gst_number);

CREATE INDEX IF NOT EXISTS idx_customers_name
    ON customers (customer_name);

-- Up to 5 contact persons per customer (name + email each)
CREATE TABLE IF NOT EXISTS customer_contacts (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER     NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    position        INTEGER     NOT NULL CHECK (position BETWEEN 1 AND 5),
    contact_name    TEXT        NOT NULL DEFAULT '',
    email           TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (customer_id, position)
);

CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer
    ON customer_contacts (customer_id);

-- ---------------------------------------------------------------------------
-- test_requests  (one row per Customer Test Request form)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_requests (
    id                  SERIAL PRIMARY KEY,
    customer_id         INTEGER     NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,

    request_date        DATE,                      -- Form "Date"
    lab_code            TEXT,                      -- Form "Lab Code"

    number_of_samples   INTEGER,                   -- Count of samples received
    sampling_by_lab     BOOLEAN,                   -- Sampling Done by Laboratory
    storage_temperature TEXT,                      -- e.g. Ambient / 2-8°C
    test_method_spec    TEXT,                      -- Method / specification to follow
    decision_rule       BOOLEAN,                   -- Decision Rule required?
    service_type        TEXT,                      -- 'Urgent' | 'Regular'
    delivery_mode       TEXT,                      -- Collect | Courier | Email/Whatsapp
    payment_details     TEXT,                      -- Advance / amount / remarks
    sample_description  TEXT,                      -- Free-text description block
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_requests_customer
    ON test_requests (customer_id);

CREATE INDEX IF NOT EXISTS idx_test_requests_date
    ON test_requests (request_date);

-- ---------------------------------------------------------------------------
-- sample_test_packages  (versioned test sets per product name + package type)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sample_test_packages (
    id                  SERIAL PRIMARY KEY,
    sample_product_name TEXT        NOT NULL,
    package_type        TEXT        NOT NULL
                        CHECK (package_type IN (
                            'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
                        )),
    category            TEXT        NOT NULL DEFAULT 'food'
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro')),
    current_version_no  INTEGER     NOT NULL DEFAULT 1
                        CHECK (current_version_no >= 1),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sample_test_packages_unique_active
    ON sample_test_packages (
        lower(trim(sample_product_name)),
        category
    )
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_sample_test_packages_active
    ON sample_test_packages (is_active, lower(trim(sample_product_name)));

CREATE TABLE IF NOT EXISTS sample_test_package_tests (
    package_id  INTEGER NOT NULL
                REFERENCES sample_test_packages(id) ON DELETE CASCADE,
    test_key    TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    logo_scope  TEXT    NOT NULL DEFAULT 'with_logo'
                CHECK (logo_scope IN ('with_logo', 'without_logo')),
    PRIMARY KEY (package_id, test_key)
);

CREATE INDEX IF NOT EXISTS idx_sample_test_package_tests_order
    ON sample_test_package_tests (package_id, sort_order);

-- ---------------------------------------------------------------------------
-- catalog_test_specs  (built-in test method / limits / units — Admin-editable)
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- custom_formulas  (Admin-defined tests merged into runtime catalog)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS custom_formulas (
    id                  SERIAL PRIMARY KEY,
    test_key            TEXT        NOT NULL,
    name                TEXT        NOT NULL,
    method              TEXT        NOT NULL DEFAULT '',
    unit                TEXT        NOT NULL DEFAULT '',
    category            TEXT        NOT NULL
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro')),
    package_type        TEXT
                        CHECK (
                            package_type IS NULL
                            OR package_type IN (
                                'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
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
    is_active           BOOLEAN     NOT NULL DEFAULT FALSE,
    is_validated        BOOLEAN     NOT NULL DEFAULT FALSE,
    validation_trials_json TEXT     NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_formulas_test_key_active
    ON custom_formulas (test_key)
    WHERE is_active = TRUE;

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

-- ---------------------------------------------------------------------------
-- request_samples  (rows in the "Sample Description" table)
-- Each sample gets a unique sample_code for analyst handoff.
-- Rows are retained for 50 days (expires_at); cleanup script deletes expired.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS request_samples (
    id                  SERIAL PRIMARY KEY,
    request_id          INTEGER NOT NULL REFERENCES test_requests(id) ON DELETE CASCADE,
    sr_no               INTEGER NOT NULL,              -- Serial number on the form
    sample_name         TEXT,                          -- Name of sample
    batch_code          TEXT,                          -- Code / batch no.
    quantity            TEXT,                          -- Sample qty. (kept as text for units)
    parameters          TEXT,                          -- Parameters column on CTR form

    -- Analyst workflow fields
    sample_code         TEXT        NOT NULL,        -- e.g. SLS-260717-0001
    category            TEXT        NOT NULL DEFAULT 'food'
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer', 'micro')),
    tests_to_perform    TEXT,                          -- Display names of selected tests
    tests_json          TEXT,                          -- JSON list of catalog test_keys
    status              TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_progress', 'completed', 'reported')),
    analyst_remarks     TEXT,
    assigned_analyst_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    assigned_micro_analyst_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    protocol_no         TEXT,                          -- Reception-entered; synced to sample_protocols
    report_format       TEXT        NOT NULL DEFAULT 'with_logo'
                        CHECK (report_format IN ('with_logo', 'without_logo', 'both')),
    tests_with_logo_json TEXT,
    tests_without_logo_json TEXT,
    package_id          INTEGER REFERENCES sample_test_packages(id) ON DELETE SET NULL,
    package_version_no  INTEGER,
    package_type        TEXT
                        CHECK (
                            package_type IS NULL
                            OR package_type IN (
                                'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
                            )
                        ),
    -- Reception sample verification checklist (printed on last CTR page per sample)
    verify_review_date          DATE,
    verify_lab_code             TEXT,
    verify_sample_condition     TEXT,
    verify_qty_checked          BOOLEAN,
    verify_chemical_available     BOOLEAN,
    verify_methods_available    BOOLEAN,
    verify_methods_informed     BOOLEAN,
    verify_tat_informed         BOOLEAN,
    verify_ready_to_issue       BOOLEAN,
    verify_conformity_statement BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '50 days'),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_request_samples_code_active
    ON request_samples (sample_code)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_request_samples_request
    ON request_samples (request_id);

CREATE INDEX IF NOT EXISTS idx_request_samples_code
    ON request_samples (sample_code);

CREATE INDEX IF NOT EXISTS idx_request_samples_status
    ON request_samples (status);

CREATE INDEX IF NOT EXISTS idx_request_samples_expires
    ON request_samples (expires_at);

CREATE INDEX IF NOT EXISTS idx_request_samples_category
    ON request_samples (category);

CREATE INDEX IF NOT EXISTS idx_request_samples_assigned_analyst
    ON request_samples (assigned_analyst_id, status, expires_at);

CREATE INDEX IF NOT EXISTS idx_request_samples_assigned_micro_analyst
    ON request_samples (assigned_micro_analyst_id, status, expires_at);

CREATE INDEX IF NOT EXISTS idx_request_samples_package
    ON request_samples (package_id);

-- JSON array of shared catalog test_keys, e.g. ["moisture","total_ash"]
-- Category filters which catalog tests Reception can assign.
-- Existing DBs: see scripts/migrate_protocol.sql and scripts/migrate_category.sql

-- ---------------------------------------------------------------------------
-- sample_protocols  (header page — same 2-row layout for ANY sample)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sample_protocols (
    id                  SERIAL PRIMARY KEY,
    sample_id           INTEGER     NOT NULL UNIQUE
                        REFERENCES request_samples(id) ON DELETE CASCADE,
    protocol_no         TEXT,
    issued_to           TEXT,
    issued_by           TEXT,
    sample_received_on  DATE,
    date_of_analysis    DATE,
    appearance_text     TEXT,
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- sample_test_results  (one row per shared-library test on a sample)
-- test_key e.g. moisture — same worksheet/formula for every product name.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sample_test_results (
    id                  SERIAL PRIMARY KEY,
    sample_id           INTEGER     NOT NULL
                        REFERENCES request_samples(id) ON DELETE CASCADE,
    test_key            TEXT        NOT NULL,
    test_name           TEXT        NOT NULL,
    method              TEXT,
    unit                TEXT,
    inputs_json         TEXT,
    result_value        TEXT,
    result_numeric      DOUBLE PRECISION,
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    UNIQUE (sample_id, test_key)
);

CREATE INDEX IF NOT EXISTS idx_sample_test_results_sample
    ON sample_test_results (sample_id);

-- ---------------------------------------------------------------------------
-- users  (login credentials; roles via user_roles junction — up to 2 per user)
-- ---------------------------------------------------------------------------
-- Seeded default admin (username admin / Admin@123) via scripts/seed_admin.py.
-- New staff: must_change_password = TRUE until they change it at the desk.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT        NOT NULL UNIQUE,
    password_hash        TEXT        NOT NULL,
    full_name            TEXT,
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username
    ON users (username);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id     INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role        TEXT        NOT NULL
                CHECK (role IN ('admin', 'reception', 'analyst', 'reviewer')),
    PRIMARY KEY (user_id, role)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_role
    ON user_roles (role);

-- ---------------------------------------------------------------------------
-- audit_log  (who / when / what for every meaningful write)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name    TEXT NOT NULL,
    action       TEXT NOT NULL,
    entity_table TEXT NOT NULL,
    entity_id    TEXT,
    details      TEXT,
    edit_reason  TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at
    ON audit_log (occurred_at DESC);

-- ---------------------------------------------------------------------------
-- entity_versions  (immutable snapshot before each edit)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_versions (
    id              BIGSERIAL PRIMARY KEY,
    entity_table    TEXT        NOT NULL,
    entity_id       TEXT        NOT NULL,
    version_no      INTEGER     NOT NULL,
    snapshot_json   TEXT        NOT NULL,
    edit_reason     TEXT        NOT NULL,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name       TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_table, entity_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_entity_versions_entity
    ON entity_versions (entity_table, entity_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_entity_versions_created_at
    ON entity_versions (created_at DESC);

-- ---------------------------------------------------------------------------
-- Auto-update customers.updated_at / users.updated_at on any change
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_customers_updated_at ON customers;
CREATE TRIGGER trg_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE PROCEDURE set_updated_at();

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE PROCEDURE set_updated_at();
