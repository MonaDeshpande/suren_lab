-- Appearance master lookup for Analyst window
CREATE TABLE IF NOT EXISTS appearance_master (
    id              SERIAL PRIMARY KEY,
    appearance_text TEXT        NOT NULL,
    normalized_key  TEXT        NOT NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_appearance_master_normalized
    ON appearance_master (normalized_key)
    WHERE is_active = TRUE;

INSERT INTO appearance_master (appearance_text, normalized_key)
SELECT DISTINCT trim(appearance_text), lower(trim(appearance_text))
  FROM sample_protocols
 WHERE coalesce(trim(appearance_text), '') <> ''
   AND NOT EXISTS (
       SELECT 1 FROM appearance_master am
        WHERE am.normalized_key = lower(trim(sample_protocols.appearance_text))
   );
