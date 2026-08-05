-- =============================================================================
-- Migration: customer_contacts (up to 5 contact persons per customer)
-- Run: docker exec -i sls_lab_db psql -U sls_user -d sls_lab < scripts/migrate_contacts.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS customer_contacts (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER     NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    position        INTEGER     NOT NULL CHECK (position BETWEEN 1 AND 5),
    contact_name    TEXT        NOT NULL DEFAULT '',
    email           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (customer_id, position)
);

CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer
    ON customer_contacts (customer_id);

-- Backfill primary contact from legacy customers columns
INSERT INTO customer_contacts (customer_id, position, contact_name, email)
SELECT c.id, 1, COALESCE(c.contact_person, ''), COALESCE(c.email, '')
  FROM customers c
 WHERE NOT EXISTS (
     SELECT 1 FROM customer_contacts cc WHERE cc.customer_id = c.id
 )
   AND (COALESCE(c.contact_person, '') <> '' OR COALESCE(c.email, '') <> '');
