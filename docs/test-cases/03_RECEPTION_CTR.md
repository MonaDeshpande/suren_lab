# Reception / CTR — Test Cases

**Module:** Customer Test Request intake  
**Related code:** `pages/1_Reception.py`, `ui/components.py`, `services/requests.py`, `services/customers.py`, `services/test_packages.py`, `services/pdf_generator.py`, `services/docx_filler.py`  
**Access:** `admin`, `reception`

**UI layout (sample intake):**
- **Sections 3–5 — Printed CTR:** matches LLP.docx (customer, request header, 5-column sample table). Lab Code (`SLS/26/306`) is the primary identifier; Code/batch no. is optional customer reference.
- **Section 6 — Lab workflow (not printed):** per-row Sample ID preview (derived from Lab Code, with `/1`, `/2` suffixes for multiple samples), assigned analyst, report format.

---

## TC-REC-001 — Save CTR happy path (single sample)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as reception; DB connected |
| **Steps** | 1. Fill customer: name, GST, contact person, contact number, email (address optional for validator). 2. Set request date (today). 3. Add sample name; select ≥1 catalog test. 4. **Save & Generate Form**. |
| **Expected** | Save succeeds; sample code shown (`SLS/26/306` for single sample); PDF download available; status of sample `pending`. |
| **Postconditions** | Rows in `customers`, `test_requests`, `request_samples`; audit `request.save` and `report.ctr` (if PDF OK). |

---

## TC-REC-002 — Multi-sample CTR

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Set Lab Code `SLS/26/306`; add 3 sample rows with names + catalog tests; save. |
| **Expected** | Three sample codes: `SLS/26/306/1`, `SLS/26/306/2`, `SLS/26/306/3`. |

---

## TC-REC-003 — Validation: missing customer name

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Leave customer name blank; fill other required fields; save. |
| **Expected** | Error: Customer details (name) are required. No DB save. |

---

## TC-REC-004 — Validation: missing GST

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Omit GST; save. |
| **Expected** | Error: GST number is required. |

---

## TC-REC-005 — Validation: missing contact person / number / email

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Separately omit contact person, then number, then email. |
| **Expected** | Matching required-field errors for each. |

---

## TC-REC-006 — Validation: missing request date

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Clear date if possible; save. |
| **Expected** | Error: Date is required. |

---

## TC-REC-007 — Validation: no sample rows

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Leave all sample rows empty; save. |
| **Expected** | Error: Add at least one sample row. |

---

## TC-REC-008 — Validation: sample name missing

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Fill batch/qty but leave sample name empty with tests selected (or equivalent non-empty row without name). |
| **Expected** | Error for that Sr. No requiring sample name. |

---

## TC-REC-009 — Validation: no catalog tests and no parameters

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Sample with name but no catalog tests and empty parameters. |
| **Expected** | Error: select at least one catalog test. |

---

## TC-REC-010 — Empty sample rows skipped

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Steps** | Fill sample 1; leave sample 2 completely blank; save. |
| **Expected** | Only sample 1 saved; no error for blank trailing row. |

---

## TC-REC-011 — Customer upsert by GST

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | 1. Save CTR with GST `27AAAAA0000A1Z5`, name Company A. 2. Save another CTR same GST, updated name/contact. |
| **Expected** | One permanent customer; fields updated; GST stored uppercase; audit `customer.upsert`. |

---

## TC-REC-012 — Customer search / picker

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Existing customers in DB |
| **Steps** | Search by partial GST or name; select existing customer. |
| **Expected** | Form fields populate from selected customer. Empty search may show recent customers. |

---

## TC-REC-013 — Sample code format (lab-code derived)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Steps** | Set Lab Code `SLS/26/306`; save one sample; then save a CTR with two samples using the same lab code. |
| **Expected** | Single sample → `SLS/26/306`; two samples → `SLS/26/306/1` and `SLS/26/306/2`. Section 6 previews IDs live before save. |

---

## TC-REC-014 — Single sample uses lab code without suffix

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Steps** | Set Lab Code `SLS/26/307`; add one sample row; save. |
| **Expected** | Sample code equals lab code exactly: `SLS/26/307` (no `/1` suffix). |

---

## TC-REC-015 — Shared catalog applies to all samples

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Select Moisture + Total ash; add two sample names; save. |
| **Expected** | Both samples store same selected test keys / display names. |

---

## TC-REC-016 — Sample expires_at is ~10 days

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Save CTR; inspect DB `request_samples.expires_at` (or note creation time). |
| **Expected** | `expires_at` ≈ `created_at + 10 days`. Initial status `pending`. |

---

## TC-REC-017 — PDF generated with stamp

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | After successful save, download filled PDF. |
| **Expected** | PDF downloads; contains customer/sample data; generated-by / datetime stamp present when implemented. |

---

## TC-REC-018 — DOCX optional / PDF still OK

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | Missing Word template or Word conversion failure possible |
| **Steps** | Save CTR; attempt Word download. |
| **Expected** | If DOCX fails, PDF still available; user sees warning for Word, not total failure. |

---

## TC-REC-019 — Lab code and optional fields persist

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Steps** | Fill lab code, service type Urgent, delivery Courier, storage, payment remarks; save. |
| **Expected** | Values stored on `test_requests` and appear on generated form / reviewer reception block. |

---

## TC-REC-020 — Parameters-only path (no catalog keys)

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Notes** | If UI allows free-text parameters without catalog, validator accepts when parameters non-empty. |
| **Expected** | Save OK; `tests_json` may be null; analyst may see full catalog fallback. |

---

## TC-REC-021 — Edit existing CTR requires reason

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Saved CTR in DB |
| **Steps** | Open **Edit existing request** tab; search and select request; change lab code or sample name; enter edit reason (≥10 chars); save. |
| **Expected** | Request updated; audit `request.update` with edit reason; version row in `entity_versions`; CTR PDF regenerates. |

---

## TC-REC-022 — Edit blocked without reason

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Edit existing request; leave edit reason blank or &lt;10 chars; save. |
| **Expected** | Save blocked with validation error; no DB change. |

---

## TC-REC-023 — Customer update on new CTR requires reason

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Pick existing customer (or reuse GST); change name/address; provide edit reason; save new CTR. |
| **Expected** | Customer updated; audit `customer.update`; version snapshot saved; new request still created. |

---

## TC-REC-025 — Analyst assignment required per sample

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Save CTR with sample name/code/tests but no analyst selected in **Section 6**. |
| **Expected** | Error: assign an analyst; no DB save. |

---

## TC-REC-024 — Sample code locked after analyst starts

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Preconditions** | Sample with status `in_progress` or later |
| **Steps** | Edit request; attempt to change locked sample code or remove row. |
| **Expected** | Update rejected with clear error; UI warns which codes are locked. |

---

## TC-REC-026 — Report format per sample

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | On a sample row, choose **A — With Logo**, **B — Without Logo**, or **Both**. Save CTR. |
| **Expected** | `report_format` stored on `request_samples`; post-save table shows format label. Default for new rows: A — With Logo. |

---

## TC-REC-027 — Both format: logo sets from package

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Food test package defines both with-logo and without-logo test lists (disjoint) |
| **Steps** | Select **Both** report format on a sample row whose package has both sets. Save. |
| **Expected** | `tests_with_logo_json` and `tests_without_logo_json` store the package's respective catalog keys; `tests_json` is the union for analyst work; validation passes. |

---

## TC-REC-028 — Both format validation (package sets)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Select **Both** when the resolved package has only with-logo tests (no without-logo set), or only without-logo tests. Save. |
| **Expected** | Validation error; no DB save. |

---

## TC-REC-029 — Create Food test package (dual logo sets)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as reception; DB connected |
| **Steps** | Open **Test packages** tab. Enter product name (e.g. Jaggery), test type FSSAI, select **With logo tests** and **Without logo tests** (no overlap). **Create package**. |
| **Expected** | Rows in `sample_test_package_tests` with `logo_scope` `with_logo` / `without_logo`; version 1; audit `package.create`. |

---

## TC-REC-030 — CTR Food row resolves package tests

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Package exists for Jaggery + FSSAI |
| **Steps** | New CTR → **Section 5** Food row: name **Jaggery**, Parameters **FSSAI**; **Section 6**: sample code, analyst, report format. Save. |
| **Expected** | Tests auto-loaded from package; `parameters` shows `Jaggery — FSSAI — tests to be conducted`; `package_id`, `package_version_no`, `package_type` stored on `request_samples`. |

---

## TC-REC-031 — Missing package blocks save

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Food row with sample name + Parameters (test type) but no matching active package. Save. |
| **Expected** | Validation error directing user to **Test packages** tab; no DB save. |

---

## TC-REC-032 — Package update creates version

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Edit package tests with edit reason ≥10 chars. Save. |
| **Expected** | `current_version_no` increments; prior state in `entity_versions`; **Compare versions** shows added/removed tests highlighted. |

---

## TC-REC-033 — Package version pinned on sample

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Save CTR using package v1. Update package to v2. Re-open saved CTR. |
| **Expected** | Sample still references `package_version_no` from intake (v1 tests unchanged on that row). |

---

## TC-REC-034 — Activate deactivated package

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Inactive Food test package exists; no other active package for same product + type |
| **Steps** | Open **Test packages** → select inactive package → enter edit reason ≥10 chars → **Activate package**. |
| **Expected** | `is_active = TRUE`; package resolves at CTR intake; audit `package.activate`; version snapshot archived. |

---

## TC-REC-035 — Sample shows package defined / not defined

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | On New/Edit CTR, enter Food sample name + Parameters. Observe **Package assignment** block per row. Save request and review post-save sample table. |
| **Expected** | Row shows **Defined** / **Not defined** / **Inactive** with package `#id`, version, and WL/NWL detail; saved table includes **Package**, **Pkg version**, and **Package status** columns. Edit mode shows **Intake package** pinned version when reopening a saved CTR. |

---

## TC-REC-036 — Micro category auto-assigns 6 tests

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as reception |
| **Steps** | Select sample category **Micro**; fill customer + sample name; assign analyst + protocol no; save. |
| **Expected** | All 6 microbiological tests auto-assigned (TPC, T.coliform, E. Coli, Salmonella, S. aureus, Yeast and Mould). No Parameters package selection. Sample status `pending`. |
| **Automated** | `test_validation.py::test_micro_category_with_bundle_ok`, `test_formulas.py::test_micro_tests_count` |

---

## Known gap (exploratory)

| ID | Note |
|----|------|
| TC-REC-EXP-01 | UI may mark Address with `*`; `validate_request` does **not** require address — document actual behaviour. |
| TC-REC-EXP-02 | No GST format / checksum validation. |
