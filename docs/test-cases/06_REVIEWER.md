# Reviewer — Test Cases

**Module:** Final Test Report (QSF 7.8.2)  
**Related code:** `pages/3_Reviewer.py`, `services/test_report_pdf.py`, `services/samples.py`  
**Access:** `admin`, `reviewer`

---

## TC-REV-001 — Review reception + analyst data

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Sample with CTR data, protocol header, ≥1 result |
| **Steps** | Find sample; open reviewer view. |
| **Expected** | Reception block (customer, sample meta) and analyst results visible read-only. |

---

## TC-REV-002 — Cannot generate without protocol header

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Sample has results but no protocol header |
| **Steps** | Attempt **Generate Final Report**. |
| **Expected** | Blocked: cannot generate until protocol header and at least one test result are saved. Status unchanged. |

---

## TC-REV-003 — Cannot generate without results

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Header saved; zero results |
| **Steps** | Generate Final Report. |
| **Expected** | Same precondition error; status unchanged. |

---

## TC-REV-004 — Generate Final Report happy path

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Header + ≥1 result; status preferably `completed` |
| **Steps** | Optionally add reviewer_note; click **Generate Final Report**; download PDF. |
| **Expected** | PDF generated; status → `reported`; audit `report.final`; download works. |

---

## TC-REV-005 — Warning on pending (non-blocking)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | Sample still `pending` but has header + result |
| **Steps** | Open reviewer; generate. |
| **Expected** | Warning that analysis may not have started; generation still allowed if preconditions met. |

---

## TC-REV-006 — Warning on in_progress (non-blocking)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | Status `in_progress` with header + results |
| **Steps** | Generate. |
| **Expected** | Warning analyst may not be finished; can still generate; status becomes `reported`. |

---

## TC-REV-007 — Already reported info

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Preconditions** | Status already `reported` |
| **Steps** | Open sample. |
| **Expected** | Info that report already generated; regenerating not prevented. |

---

## TC-REV-008 — Reviewer note appended to remarks

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Enter reviewer note `Approved for release`; generate. |
| **Expected** | Sample remarks include prior analyst_remarks plus `[Reviewer] Approved for release` (or equivalent append). |

---

## TC-REV-009 — PDF stamp generated_by / datetime

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Generate as logged-in reviewer; open PDF. |
| **Expected** | Stamp shows generator (full_name or username) and Asia/Kolkata datetime format. |

---

## TC-REV-010 — PDF failure does not mark reported

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Notes** | Simulate only if feasible (broken env); otherwise exploratory. |
| **Expected** | On exception before status update, status remains previous; error shown. |

---

## TC-REV-011 — Incomplete vs assigned tests still allowed

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Boundary |
| **Preconditions** | Reception assigned 5 tests; analyst saved 1 |
| **Steps** | Generate final report. |
| **Expected** | Allowed (no completeness gate); PDF shows available results. |

---

## TC-REV-012 — Search / queue for non-expired samples

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Search and select from queue. |
| **Expected** | Only non-expired samples appear. |

---

## TC-REV-013 — Analyst denied Reviewer page

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Expected** | Access denied. |
