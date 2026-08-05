-- Reception-entered protocol number per sample (synced to sample_protocols on save).
ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS protocol_no TEXT;
