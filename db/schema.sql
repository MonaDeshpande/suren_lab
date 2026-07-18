-- =============================================================================
-- SLS Food Testing Lab — Database Schema
-- Customer Test Request system
-- =============================================================================
-- Permanent customer master + per-request intake records.
-- GST number is the unique business key for customers.
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
    gst_number      TEXT        NOT NULL UNIQUE,   -- GSTIN — unique key
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookup by GST or partial name search
CREATE INDEX IF NOT EXISTS idx_customers_gst
    ON customers (gst_number);

CREATE INDEX IF NOT EXISTS idx_customers_name
    ON customers (customer_name);

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

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_requests_customer
    ON test_requests (customer_id);

CREATE INDEX IF NOT EXISTS idx_test_requests_date
    ON test_requests (request_date);

-- ---------------------------------------------------------------------------
-- request_samples  (rows in the "Sample Description" table)
-- Each sample gets a unique sample_code for analyst handoff.
-- Rows are retained for 10 days (expires_at); cleanup script deletes expired.
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
    sample_code         TEXT        NOT NULL UNIQUE,   -- e.g. SLS-260717-0001
    category            TEXT        NOT NULL DEFAULT 'food'
                        CHECK (category IN ('food', 'water', 'cattle_feed_fertilizer')),
    tests_to_perform    TEXT,                          -- Display names of selected tests
    tests_json          TEXT,                          -- JSON list of catalog test_keys
    status              TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_progress', 'completed', 'reported')),
    analyst_remarks     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 days')
);

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
    UNIQUE (sample_id, test_key)
);

CREATE INDEX IF NOT EXISTS idx_sample_test_results_sample
    ON sample_test_results (sample_id);

-- ---------------------------------------------------------------------------
-- users  (login credentials + single role per account)
-- ---------------------------------------------------------------------------
-- Seeded default admin (username admin / Admin@123) via scripts/seed_admin.py.
-- New staff: must_change_password = TRUE until they change it at the desk.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT        NOT NULL UNIQUE,
    password_hash        TEXT        NOT NULL,
    full_name            TEXT,
    role                 TEXT        NOT NULL
                         CHECK (role IN ('admin', 'reception', 'analyst', 'reviewer')),
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username
    ON users (username);

CREATE INDEX IF NOT EXISTS idx_users_role
    ON users (role);

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
    details      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at
    ON audit_log (occurred_at DESC);

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
