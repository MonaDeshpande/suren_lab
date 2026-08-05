# Analyst — Test Cases

**Module:** Protocol worksheets, results, status, protocol documents  
**Related code:** `pages/2_Analyst.py`, `services/protocol_store.py`, `services/protocol_docx.py`, `services/protocol_pdf.py`  
**Access:** `admin`, `analyst`

---

## Analyst protocol flow (validated)

Reception assigns tests → Analyst finds sample → saves header → performs each assigned test (worksheet inputs → **Calculate & save** → auto-calculated result) → reviews page-1 summary → generates protocol PDF/DOCX from reference template → **prints and signs offline** (pen on blank signature blocks).

| Sample type | Reception test assignment | Protocol template |
|-------------|---------------------------|-------------------|
| **Water** | All 11 water tests auto-included | `reference/Water protocol 2025.docx` |
| **Micro** | All 6 micro tests auto-included | No analyst protocol DOCX — Reviewer generates Micro Test Report |
| **Food (Basic Nutrition)** | Multiselect `bn_*` tests at Reception | `reference/Basic Nutrition Protocol 2026.docx` when any `bn_*` key selected |
| **Food (Jaggery)** | Multiselect Jaggery tests at Reception | `reference/Jaggery Protocol LLP.docx` |

**Page-1 Method column:** Fixed per test in the Word template (e.g. `IS 3025 : Part 11`). Generation fills **Result** only, not Method. Same method strings appear in the Analyst UI from `test_catalog.py`.

**Signing:** App downloads PDF/DOCX only. Checked By / Dated blocks stay blank for manual pen sign-off after printing. Customer-facing **Test Report** is generated separately by Reviewer.

**Automated coverage:** `tests/unit/test_protocol_flow.py`

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

## TC-ANL-002 — Search by lab code / sample name

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Use each search mode (`lab_code`, `sample`) with known partial strings. Client name search is not available to Analyst. |
| **Expected** | Matching open samples returned (limit ~50). Blank query → empty list. No Client column in results. |

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

## TC-ANL-021 — Pure analyst sees only assigned samples

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Two analyst users; reception assigned sample A to analyst 1 only |
| **Steps** | Login as analyst 1 → search/open sample A. Login as analyst 2 → same search. |
| **Expected** | Analyst 1 sees sample; analyst 2 does not. Admin on Analyst page sees all. |

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

## TC-ANL-012 — Empty tests_json → full category catalog fallback

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | Sample with null/empty tests_json |
| **Steps** | Open analyst worksheet selector for food or water sample. |
| **Expected** | Full catalog for that category (21 food keys or 11 water keys). |

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
| **Expected** | Word and PDF files generate for Food, Water, and Basic Nutrition samples when Microsoft Word or LibreOffice is available on the host PC; audit `report.protocol`. If PDF conversion fails, UI shows the specific error. Without header → warning to save header first. |

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

---

## TC-ANL-020 — Water sample: all 11 tests auto-assigned at Reception

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | CTR saved with category Water |
| **Steps** | Open sample on Analyst page; inspect test selector. |
| **Expected** | All 11 water protocol tests available (pH, TDS, chlorides, …). No manual multiselect at Reception. |
| **Automated** | `test_protocol_flow.py::TestTemplateRouting::test_water_auto_assigns_eleven_tests_at_reception` |

---

## TC-ANL-021 — Water protocol uses Water protocol 2025.docx template

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Save ≥1 water result; generate protocol document. |
| **Expected** | Output based on `reference/Water protocol 2025.docx`; page-1 summary has 11 fixed method rows (results filled in place; unused rows remain blank). |
| **Automated** | `test_protocol_flow.py::TestWaterProtocolGeneration` |

---

## TC-ANL-022 — Basic Nutrition food uses Basic Nutrition Protocol 2026.docx

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Food sample with any `bn_*` test assigned at Reception |
| **Steps** | Save result; generate protocol. |
| **Expected** | Output based on `reference/Basic Nutrition Protocol 2026.docx`. |
| **Automated** | `test_protocol_flow.py::TestTemplateRouting::test_nutrition_food_uses_basic_nutrition_template` |

---

## TC-ANL-023 — Jaggery food uses Jaggery Protocol LLP.docx

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Food sample with Jaggery-only tests (no `bn_*` keys) |
| **Steps** | Save result; generate protocol. |
| **Expected** | Output based on `reference/Jaggery Protocol LLP.docx`. |
| **Automated** | `test_protocol_flow.py::TestTemplateRouting::test_jaggery_food_uses_jaggery_template` |

---

## TC-ANL-024 — Page-1 Method column fixed; Result filled from saved data

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Generate water or Basic Nutrition protocol with saved results. Open DOCX; compare page-1 Method vs Result columns. |
| **Expected** | Method text matches reference template (not overwritten from DB). Result column shows saved calculated values only for completed tests. |
| **Automated** | `test_protocol_flow.py::TestWaterProtocolGeneration`, `TestNutritionProtocolGeneration` |

---

## TC-ANL-025 — Protocol download for print; manual pen signature offline

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Generate protocol PDF/DOCX; inspect signature area and footer. |
| **Expected** | Footer shows Prepared by / Reviewed & Issued by / Approved by rows (director name/signature blank for pen sign-off). No body Analyzed By / Checked By blocks. No Generated-by stamp in protocol body. No in-app digital signature. |
| **Automated** | `test_protocol_flow.py::TestOfflineSignature` |

---

## TC-ANL-026 — Micro sample: result-only entry for fixed 6-test panel

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | CTR saved with category Micro (6 tests auto-assigned) |
| **Steps** | Open sample; for each test enter Result (e.g. Absent); Calculate & save; set status completed. |
| **Expected** | All 6 tests available. Limits and Method shown as fixed captions (not editable). No protocol DOCX generate section — caption directs to Reviewer final report. |
| **Automated** | `test_micro_report.py` |
