-- Migration: GST number optional on customers (nullable; unique when provided)
-- Safe to re-run.

ALTER TABLE customers
    ALTER COLUMN gst_number DROP NOT NULL;

DROP INDEX IF EXISTS idx_customers_gst_active;

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_gst_active
    ON customers (gst_number)
    WHERE is_active = TRUE AND gst_number IS NOT NULL;
