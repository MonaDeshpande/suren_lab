# Reception / CTR — Test Cases

**Module:** Customer Test Request intake  
**Related code:** `pages/1_Reception.py`, `services/requests.py`, `services/customers.py`, `services/pdf_generator.py`, `services/docx_filler.py`  
**Access:** `admin`, `reception`

---

## TC-REC-001 — Save CTR happy path (single sample)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as reception; DB connected |
| **Steps** | 1. Fill customer: name, GST, contact person, contact number, email (address optional for validator). 2. Set request date (today). 3. Add sample name; select ≥1 catalog test. 4. **Save & Generate Form**. |
| **Expected** | Save succeeds; sample code shown (`SLS-YYMMDD-NNNN`); PDF download available; status of sample `pending`. |
| **Postconditions** | Rows in `customers`, `test_requests`, `request_samples`; audit `request.save` and `report.ctr` (if PDF OK). |

---

## TC-REC-002 — Multi-sample CTR

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Add 3 sample rows with names + catalog tests; save. |
| **Expected** | Three unique sample codes; same date prefix; sequence increments (…0001, 0002, 0003). |

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

## TC-REC-013 — Sample code format and sequencing

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Steps** | Save two CTRs on same request date. Note codes. |
| **Expected** | Format `SLS-YYMMDD-NNNN` where YYMMDD matches request date; sequence increases. |

---

## TC-REC-014 — Backdated request_date affects code prefix

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Steps** | Set request date to a past date; save. |
| **Expected** | Sample code prefix uses that date’s YYMMDD, not necessarily today. |

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

## Known gap (exploratory)

| ID | Note |
|----|------|
| TC-REC-EXP-01 | UI may mark Address with `*`; `validate_request` does **not** require address — document actual behaviour. |
| TC-REC-EXP-02 | No GST format / checksum validation. |
