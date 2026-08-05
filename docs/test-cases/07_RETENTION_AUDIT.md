# Retention & Audit — Test Cases

**Module:** 10-day sample retention, purge, audit trail  
**Related code:** `services/samples.py` (`delete_expired_samples`), `app.py`, `pages/1_Reception.py`, `scripts/cleanup_expired_samples.py`, `services/audit.py`

---

## Retention

### TC-RET-001 — New sample has 10-day expiry

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Save CTR; inspect `expires_at`. |
| **Expected** | Approximately now + 10 days. |

---

### TC-RET-002 — Non-expired sample visible

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Search sample within retention window on Analyst/Reviewer. |
| **Expected** | Found. |

---

### TC-RET-003 — Expired sample not readable via get_by_code

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Force `expires_at` in past via SQL for a test sample (lab/test DB only). |
| **Steps** | Lookup by sample code in UI/service. |
| **Expected** | Not found (`expires_at > NOW()` filter). |

---

### TC-RET-004 — Purge on app home after login

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | ≥1 expired sample row exists |
| **Steps** | Login; open home (DB OK). |
| **Expected** | Info if deleted count > 0; expired rows removed; session flag prevents duplicate home purge. |

---

### TC-RET-005 — Purge on Reception page load

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Notes** | Separate session flag `_reception_purged` may also run purge. |
| **Expected** | Expired samples deleted if any remain. |

---

### TC-RET-006 — CLI cleanup script

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Run `python scripts/cleanup_expired_samples.py` with expired rows present. |
| **Expected** | Prints deleted count; rows gone. Actor may be `system` in audit. |

---

### TC-RET-007 — Customers permanent after sample purge

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Customer used on purged sample |
| **Steps** | After purge, search customer by GST in Reception. |
| **Expected** | Customer still exists and selectable. |

---

### TC-RET-008 — test_requests header retained after sample purge

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | After sample delete, check `test_requests` for that request_id. |
| **Expected** | Header row still present (samples cascade-deleted from `request_samples`). |

---

### TC-RET-009 — Cascade deletes protocol/results with sample

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Sample had protocol + results; then expired and purged |
| **Expected** | Related `sample_protocols` / `sample_test_results` removed via FK CASCADE. |

---

### TC-RET-010 — Reported samples still visible until expiry

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Boundary |
| **Preconditions** | Status `reported`, not yet expired |
| **Expected** | Still searchable until `expires_at`. |

---

## Audit matrix

| Action | entity_table | Trigger | TC |
|--------|--------------|---------|-----|
| `user.create` | users | Admin create user | TC-AUD-001 |
| `user.set_roles` | users | Admin change roles | TC-AUD-002 |
| `user.set_active` | users | Activate/deactivate | TC-AUD-003 |
| `user.reset_password` | users | Reset password | TC-AUD-004 |
| `customer.upsert` | customers | CTR save | TC-AUD-005 |
| `request.save` | test_requests | CTR save | TC-AUD-006 |
| `report.ctr` | test_requests | CTR PDF success | TC-AUD-007 |
| `sample.status` | request_samples | Status update | TC-AUD-008 |
| `sample.purge_expired` | request_samples | Purge with deletions | TC-AUD-009 |
| `protocol.upsert` | sample_protocols | Header save | TC-AUD-010 |
| `result.save` | sample_test_results | Worksheet save | TC-AUD-011 |
| `report.protocol` | request_samples | Protocol doc | TC-AUD-012 |
| `report.final` | request_samples | Final report | TC-AUD-013 |

---

### TC-AUD-001 … TC-AUD-013 — Action recorded

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Perform each trigger above; open Admin audit log (or query `audit_log`). |
| **Expected** | Row with correct `action`, `user_name`, `entity_table`, timestamp; newest first. |

---

### TC-AUD-014 — Login/logout not audited (known gap)

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Exploratory |
| **Expected** | Document that login/logout/failed login do **not** write audit rows (current behaviour). |

---

### TC-AUD-015 — Missing audit_log table does not break saves

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Boundary |
| **Notes** | Only on mis-migrated DB; audit helpers swallow errors. |
| **Expected** | Business save still succeeds; Admin may show migration hint. |
