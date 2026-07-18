# Analyst — Test Cases

**Module:** Protocol worksheets, results, status, protocol documents  
**Related code:** `pages/2_Analyst.py`, `services/protocol_store.py`, `services/protocol_docx.py`, `services/protocol_pdf.py`  
**Access:** `admin`, `analyst`

---

## TC-ANL-001 — Find sample by sample code

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Non-expired sample from Reception exists |
| **Steps** | Search by sample code (exact / case variation). |
| **Expected** | Sample record loads with reception tests and status. |

---

## TC-ANL-002 — Search by lab code / sample name / client

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Use each search mode (`lab_code`, `sample`, `client`) with known partial strings. |
| **Expected** | Matching open samples returned (limit ~50). Blank query → empty list. |

---

## TC-ANL-003 — Open queue filter by status

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Filter queue: all / pending / in_progress / completed. |
| **Expected** | List matches filter; `reported` typically not in analyst filter options. |

---

## TC-ANL-004 — Save protocol header

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Enter protocol_no, issued_to, issued_by, dates, appearance_text; **Save header**. |
| **Expected** | Header persisted; audit `protocol.upsert`. |

---

## TC-ANL-005 — Calculate & save moisture result

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Sample assigned Moisture (or full catalog fallback) |
| **Steps** | Select moisture; enter W1=10.5, W=5.0, W2=10.2; Calculate & save. |
| **Expected** | Result display `6.0` (or `6`); `result_numeric=6.0`; audit `result.save`. |

---

## TC-ANL-006 — First result auto-sets in_progress

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Sample status `pending` |
| **Steps** | Save any valid test result. |
| **Expected** | Status becomes `in_progress` automatically; audit `sample.status`. |

---

## TC-ANL-007 — Missing required worksheet inputs

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Leave required numeric fields blank; Calculate & save. |
| **Expected** | Missing-field popup/dialog listing required labels; no bad result saved. |

---

## TC-ANL-008 — Zero sample weight rejected (moisture)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Steps** | Set W=0 for moisture; calculate. |
| **Expected** | Error: Sample weight W cannot be zero. |

---

## TC-ANL-009 — Dry-basis requires moisture first

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Without moisture saved and without moisture_pct, calculate Total ash. |
| **Expected** | Error requiring moisture (save Moisture first or enter moisture_pct). |

---

## TC-ANL-010 — Dry-basis with moisture_pct override

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | On Total ash worksheet enter moisture_pct without prior moisture save; calculate. |
| **Expected** | Dry-basis result computed using override. |

---

## TC-ANL-011 — Assigned tests restrict selectbox

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Sample has `tests_json` with subset of keys |
| **Steps** | Open worksheet test selector. |
| **Expected** | Only assigned keys available. |

---

## TC-ANL-012 — Empty tests_json → full catalog fallback

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | Sample with null/empty tests_json |
| **Steps** | Open analyst worksheet selector. |
| **Expected** | All 11 catalog tests available. |

---

## TC-ANL-013 — Appearance copies to protocol header

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Steps** | Save appearance test with observation text. |
| **Expected** | Result saved; protocol `appearance_text` updated from observation when implemented. |

---

## TC-ANL-014 — Overwrite existing result

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Save moisture twice with different inputs. |
| **Expected** | Upsert on `(sample_id, test_key)`; latest values shown. |

---

## TC-ANL-015 — Generate protocol document

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Header saved; ≥1 result preferred |
| **Steps** | Click Generate protocol document; download PDF/DOCX. |
| **Expected** | Files generate; audit `report.protocol`. Without header → warning to save header first. |

---

## TC-ANL-016 — Manual status to completed

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Set status to `completed` with optional remarks; update. |
| **Expected** | Status `completed`; remarks stored; analyst dropdown does not offer `reported`. |

---

## TC-ANL-017 — Manual status back to pending

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Boundary |
| **Steps** | From in_progress set status to pending. |
| **Expected** | Allowed by service (no strict state machine in UI). |

---

## TC-ANL-018 — Expired sample not found

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Preconditions** | Sample past `expires_at` (or purged) |
| **Steps** | Search by its sample code. |
| **Expected** | Not found / not listed. |

---

## TC-ANL-019 — Reception role denied Analyst page

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Expected** | Access denied (see TC-RBAC-001). |
