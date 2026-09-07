-- =============================================================================
-- Migration: extend request_samples retention from 10 days to 50 days
-- Safe to re-run: default is idempotent; UPDATE recasts expires_at to created+50.
-- =============================================================================

ALTER TABLE request_samples
    ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '50 days');

UPDATE request_samples
   SET expires_at = created_at + INTERVAL '50 days'
 WHERE created_at IS NOT NULL;
