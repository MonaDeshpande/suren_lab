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

---

## TC-REV-014 — Final report respects per-sample format

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Reception saved sample with report format A, B, or Both (with logo split) |
| **Steps** | Open reviewer preview; generate Final Test Report PDF. |
| **Expected** | Preview shows read-only **Report format** (and with/without logo test lists for Both). PDF letterhead uses logo for A, blank band for B, two sections for Both. Format not editable on Reviewer page. **Report No** is the sample code (`SLS/26/691/01`, `SLS/26/691/02`, …). When format is Both, with-logo uses `{sample_code}/01` and without-logo uses `{sample_code}/02`. Footer is `page 1 of 1` (with logo) or `pg 1 of 1` (without logo). |

---

## TC-REV-015 — Water final report uses Water test report.docx layout

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Water sample with protocol header + ≥1 saved result |
| **Steps** | Open Reviewer; enter Condition, Appearance, IS 10500 limits if needed; **Generate Final Report**; download Word (and PDF if Word available). |
| **Expected** | Output matches `reference/Water test report.docx`: Chemical + Elemental on page 1, Physical on page 2, Microbiological section with **blank results** (T. Coli form, E. coli). `calcium_caco3` not on report. IS 10500 Desirable/Permissible columns populated. Chemical and Physical/Micro **Report No** fields default to the same sample code (or `{sample_code}/01` vs `/02` when format is Both). Status → `reported`. |
| **Automated** | `test_water_report_docx.py::TestWaterReportDocx` |

---

## TC-REV-016 — Micro final report matches Micro Test Report.htm

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Micro sample with protocol header + >=1 saved result |
| **Steps** | Open Reviewer; enter Condition / Customer Sample ID / Report No; preview fixed Limits and Methods; **Generate Final Report**; download Word (and PDF if Word available). |
| **Expected** | DOCX layout matches `reference/Micro Test Report.htm`: TEST REPORT title, QSF 7.8.2, metadata table, **Microbiological Test** section with 6 rows (Name / Result / Limits / Method). Limits and methods are catalog-fixed; only Results from analyst. Default **Report No** is the sample code (plus `/01` or `/02` when format is Both). Status -> `reported`. |
| **Automated** | `test_micro_report.py` |

---

## TC-REV-017 — Final report pads numeric results under 10

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Sample with saved numeric result &lt; 10 (e.g. Moisture `1.19`) |
| **Steps** | Generate Final Test Report (PDF or DOCX). |
| **Expected** | Result column shows zero-padded two-decimal format (`01.19`, `09.50`). Values ≥ 10 remain unpadded (`12.34`). Qualitative values (Absent, Agreeable) unchanged. |
| **Automated** | `test_test_report_pdf.py::test_build_test_report_data_pads_results_under_ten`, `test_number_format.py::test_format_report_number_pads_under_ten` |
