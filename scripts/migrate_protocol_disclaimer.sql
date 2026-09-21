-- Analyst-editable protocol disclaimer (per sample protocol header)
ALTER TABLE sample_protocols
    ADD COLUMN IF NOT EXISTS protocol_disclaimer_text TEXT;
