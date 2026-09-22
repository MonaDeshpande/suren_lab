# S Testing Laboratory — Test Plan

**Product:** S Testing Laboratory Customer Test Request App (S Testing Laboratory)  
**Document type:** Master Test Plan  
**Version:** 1.0  
**Scope:** Functional, RBAC, boundary, negative, and regression testing of the Streamlit + PostgreSQL LIMS

---

## 1. Objectives

1. Verify end-to-end lab workflow: Reception CTR → Analyst protocol → Reviewer Final Test Report.
2. Verify role-based access for `admin`, `reception`, `analyst`, `reviewer`.
3. Verify shared lab formula library (11 tests) for correct math and error handling.
4. Verify 50-day sample retention, purge behaviour, and audit trail.
5. Provide a repeatable regression pack for releases.

---

## 2. In scope

| Area | Coverage |
|------|----------|
| Authentication | Login, logout, forced password change, inactive users |
| RBAC | Page gates per role |
| Admin | User CRUD-lite, roles, last-admin protection, audit viewer |
| Reception / CTR | Customer upsert, validation, sample codes, PDF/DOCX |
| Analyst | Protocol header, worksheets, status, protocol documents |
| Formulas | All 11 catalog calculators + dependencies |
| Reviewer | Final report preconditions, status `reported`, PDF |
| Retention | Expiry visibility, purge (app + CLI) |
| Audit | Key write actions in `audit_log` |

---

## 3. Out of scope (v1)

- Playwright / Selenium UI automation
- Pixel-perfect PDF visual comparison (manual spot-check only)
- Performance / load / soak testing
- GST checksum, email RFC, or phone format validation (not implemented)
- Penetration testing beyond basic RBAC checks

---

## 4. Test environment

| Component | Requirement |
|-----------|-------------|
| OS | Windows 10+ (docx2pdf needs Microsoft Word for Word→PDF path) |
| App | `streamlit run app.py` — http://localhost:8501 |
| Database | PostgreSQL 16 via `docker compose up -d` (host port **5433**) |
| Seed | `python scripts/seed_admin.py` |
| Env | Copy `.env.example` → `.env` |

**DB credentials (default):** host `127.0.0.1`, port `5433`, user `sls_user`, password `sls_secure_password`, db `sls_lab`

### Default accounts

| Username | Password | Role | Notes |
|----------|----------|------|-------|
| `admin` | `Admin@123` | admin | Bootstrap; `must_change_password=FALSE` |
| (created by admin) | temporary ≥6 chars | staff | Must change password on first login |

Create dedicated test users per role before RBAC / workflow runs (see TC-ADM-001).

---

## 5. Priority definitions

| Priority | Meaning | Example |
|----------|---------|---------|
| **P0** | Blocker — release cannot ship | Login, CTR save, formula math, final report |
| **P1** | High — major feature / data integrity | RBAC, retention, last-admin guard, audit |
| **P2** | Medium/low — UX, warnings, polish | Non-blocking status warnings, optional fields |

---

## 6. Test types

| Type | Description |
|------|-------------|
| Positive | Happy path with valid data |
| Negative | Invalid / missing data rejected |
| Boundary | Limits (password length, zero weight, moisture=100) |
| RBAC | Role allow/deny matrix |
| Regression | Critical path after changes |

---

## 7. Entry criteria

- Docker Postgres healthy; migrations applied if upgrading an existing volume
- `seed_admin.py` run successfully
- App opens; login form visible
- Test users for reception / analyst / reviewer available (or create via Admin)
- For automated unit tests: `pip install -r requirements.txt` (includes pytest)

---

## 8. Exit criteria

- All **P0** cases executed; 100% pass (or defects deferred with sign-off)
- All **P1** cases executed; open P1 defects documented
- E2E smoke ([08_E2E_REGRESSION.md](08_E2E_REGRESSION.md)) passed
- `pytest -q` (unit suite) green on the release build

---

## 9. Defect severity (suggested)

| Severity | Definition |
|----------|------------|
| S1 Critical | Data loss, wrong lab result numbers, auth bypass |
| S2 Major | Workflow blocked (cannot save CTR / generate report) |
| S3 Minor | Wrong message, non-blocking UI issue |
| S4 Cosmetic | Label / layout only |

---

## 10. Test case documents

| File | Module |
|------|--------|
| [01_AUTH_RBAC.md](01_AUTH_RBAC.md) | Login & roles |
| [02_ADMIN.md](02_ADMIN.md) | User management & audit UI |
| [03_RECEPTION_CTR.md](03_RECEPTION_CTR.md) | CTR intake |
| [04_ANALYST.md](04_ANALYST.md) | Protocol workspace |
| [05_FORMULAS.md](05_FORMULAS.md) | Catalog calculations |
| [06_REVIEWER.md](06_REVIEWER.md) | Final Test Report |
| [07_RETENTION_AUDIT.md](07_RETENTION_AUDIT.md) | Expiry, purge, audit matrix |
| [08_E2E_REGRESSION.md](08_E2E_REGRESSION.md) | End-to-end & regression pack |
| [TRACEABILITY.md](TRACEABILITY.md) | Feature → TC-ID map |

### Standard TC fields

`TC-ID | Title | Module | Priority | Type | Preconditions | Steps | Expected Result | Postconditions`

---

## 11. Automated tests (how to run)

From project root (`g:\Monika\S_LAB`):

```bash
# Unit tests only (no DB required)
pytest -q

# Include integration tests (requires Docker Postgres + .env)
pytest -q -m integration

# Exclude integration
pytest -q -m "not integration"
```

See `tests/` for formula, validation, auth-hash, and optional DB integration coverage.

A successful **`run_tests.bat`** run refreshes CTR preview files under `tests/output_preview/ctr/` via [`tests/test_report_preview.py`](../tests/test_report_preview.py) (2-sample always; 5-sample ABC CTR when Postgres is up).

**App-flow document bundle** (same services as Reception / Analyst / Reviewer, not `pytest -m e2e`):

- Module: [`tests/integration/test_app_document_bundle.py`](../tests/integration/test_app_document_bundle.py)
- Included in `run_tests.bat` when Postgres is up and **Microsoft Word** (or LibreOffice) can convert DOCX → PDF
- Writes: `tests/output_preview/app_flow/{food,water,micro}/{ctr,protocol,final_report}/`
- CTR PDF uses ReportLab form layout + lab header/footer (no Word required for CTR PDF); protocol/final report still need Word/LibreOffice for PDF conversion
- Multi-sample CTR preview (5 rows, lab `SLS/26/900`): `tests/test_report_preview.py::test_ctr_multi_sample_document_bundle_writes_preview` → `tests/output_preview/ctr/`
- Dummy GST rows are removed after each category test

Manual Streamlit walkthrough (optional): see [`docs/MANUAL_PDF_QA.md`](../MANUAL_PDF_QA.md) when present.

---

## 12. Sample status lifecycle (reference)

```
pending → in_progress → completed → reported
```

- Reception creates samples as `pending` (`expires_at = now + 50 days`).
- Analyst first saved result auto-moves `pending` → `in_progress`.
- Analyst sets `completed` manually.
- Reviewer **Generate Final Report** sets `reported`.
- Service layer does **not** enforce strict transition order (UI may warn).

---

## 13. Known product gaps (exploratory / document only)

- Address marked required in UI but not enforced by `validate_request`.
- No GST / email / phone format checks.
- Same catalog test multiselect applied to all sample rows in one CTR.
- Final report allowed on `pending` / `in_progress` (warning only).
- No login/logout audit entries.
- Login/password change not rate-limited.
