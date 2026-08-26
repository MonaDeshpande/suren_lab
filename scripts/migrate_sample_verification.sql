-- Per-sample CTR verification checklist (Reception intake).
ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS verify_review_date DATE,
    ADD COLUMN IF NOT EXISTS verify_lab_code TEXT,
    ADD COLUMN IF NOT EXISTS verify_sample_condition TEXT,
    ADD COLUMN IF NOT EXISTS verify_qty_checked BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_chemical_available BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_methods_available BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_methods_informed BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_tat_informed BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_ready_to_issue BOOLEAN,
    ADD COLUMN IF NOT EXISTS verify_conformity_statement BOOLEAN;
