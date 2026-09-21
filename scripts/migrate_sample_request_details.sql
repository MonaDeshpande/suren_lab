-- Per-sample test request details + verification sample code
ALTER TABLE request_samples
    ADD COLUMN IF NOT EXISTS storage_temperature TEXT,
    ADD COLUMN IF NOT EXISTS sampling_by_lab BOOLEAN,
    ADD COLUMN IF NOT EXISTS decision_rule BOOLEAN,
    ADD COLUMN IF NOT EXISTS service_type TEXT,
    ADD COLUMN IF NOT EXISTS delivery_mode TEXT,
    ADD COLUMN IF NOT EXISTS test_method_spec TEXT,
    ADD COLUMN IF NOT EXISTS verify_sample_code TEXT;

-- Backfill from request header where sample fields are null
UPDATE request_samples rs
   SET storage_temperature = tr.storage_temperature
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.storage_temperature IS NULL
   AND tr.storage_temperature IS NOT NULL;

UPDATE request_samples rs
   SET sampling_by_lab = tr.sampling_by_lab
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.sampling_by_lab IS NULL
   AND tr.sampling_by_lab IS NOT NULL;

UPDATE request_samples rs
   SET decision_rule = tr.decision_rule
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.decision_rule IS NULL
   AND tr.decision_rule IS NOT NULL;

UPDATE request_samples rs
   SET service_type = tr.service_type
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.service_type IS NULL
   AND tr.service_type IS NOT NULL;

UPDATE request_samples rs
   SET delivery_mode = tr.delivery_mode
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.delivery_mode IS NULL
   AND tr.delivery_mode IS NOT NULL;

UPDATE request_samples rs
   SET test_method_spec = tr.test_method_spec
  FROM test_requests tr
 WHERE tr.id = rs.request_id
   AND rs.test_method_spec IS NULL
   AND tr.test_method_spec IS NOT NULL;

UPDATE request_samples rs
   SET verify_sample_code = rs.sample_code
 WHERE coalesce(trim(rs.verify_sample_code), '') = ''
   AND coalesce(trim(rs.sample_code), '') <> '';
