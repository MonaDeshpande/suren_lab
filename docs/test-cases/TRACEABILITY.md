# Feature → Test Case Traceability

Maps product features to manual TC-IDs and automated tests.

| Feature / Requirement | Manual TC-IDs | Automated |
|----------------------|---------------|-----------|
| Login success / failure | TC-AUTH-001…004 | `test_auth_rules.py` (hash/verify) |
| Case-insensitive username | TC-AUTH-005 | — |
| Forced password change | TC-AUTH-006…009 | `test_change_password_min_length` (unit rule) |
| Bootstrap admin no force-change | TC-AUTH-010 | — |
| Logout / unauthenticated gate | TC-AUTH-011…012 | — |
| RBAC page matrix | TC-RBAC-001…005, TC-ADM-016, TC-ANL-019, TC-REV-013 | — |
| Create / validate users | TC-ADM-001…006 | `test_users_admin_db.py` (create) |
| Multi-role assign / change | TC-ADM-007, 007b–d, TC-E2E-009 | `test_users_admin_db.py` + `test_users_roles.py` |
| Last-admin protection | TC-ADM-008…009, TC-ADM-020, TC-E2E-004 | `test_users_admin_db.py` |
| Activate / deactivate / reset | TC-ADM-010…013, 010a–c, 019, TC-E2E-006, TC-E2E-009 | `test_users_admin_db.py` |
| Audit viewer | TC-ADM-015, TC-AUD-* | — |
| CTR save happy / multi-sample | TC-REC-001…002, TC-E2E-001…002 | integration (optional) |
| CTR validation rules | TC-REC-003…009 | `test_validation.py` |
| Empty rows skipped | TC-REC-010 | `test_validation.py` |
| Customer GST upsert | TC-REC-011…012 | — |
| Sample code SLS-YYMMDD-NNNN | TC-REC-013…014 | integration `test_sample_code` |
| Shared catalog / expiry default | TC-REC-015…016 | — |
| CTR PDF / DOCX | TC-REC-017…018 | `tests/test_report_preview.py` |
| CTR PDF/DOCX dummy customer (DB save → generate → wipe) | TC-REC-017…018 | `tests/integration/test_dummy_document_generation.py::test_dummy_ctr_generates_pdf_and_docx` |
| Protocol water / food / micro dummy (DB → generate → wipe) | TC-ANL-015, TC-ANL-020…025 | `tests/integration/test_dummy_document_generation.py` (water/food/micro tests) |
| Multi-type CTR same customer (water + micro + food WL + food Both + cattle feed) | TC-REC-037 | `tests/test_db_integration.py`, `tests/test_report_preview.py` |
| Category per sample (DB) | TC-REC-037 | `tests/test_db_integration.py::TestCategoryPerSample` |
| Storage temperature °C (DB) | TC-REC-037 | `tests/test_db_integration.py::TestStorageTemperature` |
| Verify sample code auto-fill (DB) | TC-REC-037 | `tests/test_db_integration.py::TestVerifySampleCode` |
| Appearance master (DB) | — | `tests/test_db_integration.py::TestAppearanceMaster` |
| Analysis date range (DB) | — | `tests/test_db_integration.py::TestAnalysisDateRange` |
| Analyst search / queue | TC-ANL-001…003 | — |
| Protocol header / results | TC-ANL-004…005 | — |
| Auto in_progress | TC-ANL-006 | integration |
| Worksheet errors | TC-ANL-007…010 | `test_formulas.py` |
| Catalog restrict / fallback | TC-ANL-011…012 | — |
| Protocol document | TC-ANL-015 | — |
| Water / Nutrition / Jaggery protocol flow | TC-ANL-020…025, TC-E2E-007…008 | `test_protocol_flow.py` |
| Analyst protocol disclaimer + micro method edit | TC-ANL-028…029 | `tests/test_analyst_workflow.py` |
| Analyst workflow + protocol preview (DB) | TC-ANL-004…005, TC-ANL-026, TC-ANL-028…029 | `tests/test_analyst_workflow.py` |
| Water final report (IS 10500 layout) | TC-REV-015 | `test_water_report_docx.py` |
| Micro category + final report | TC-REC-036, TC-ANL-026, TC-REV-016 | `test_micro_report.py` |
| Status completed | TC-ANL-016 | integration |
| Appearance / moisture / ash / … (Jaggery) | TC-FOR-001…024 | `test_formulas.py` |
| Water calculations | TC-FOR-025…029 (+ existing water tests in pytest) | `test_formulas.py` |
| Basic Nutrition calculations | TC-FOR-030…037 (+ existing bn_* tests in pytest) | `test_formulas.py` |
| Food final report editable header (ULR, date, customer, sample ID, batch, lab code) | TC-REV-018 | `test_food_report_docx.py`, `test_reviewer_report_defaults.py` |
| Reviewer preconditions | TC-REV-002…003 | — |
| Final report → reported | TC-REV-004, TC-E2E-001 | — |
| Status warnings non-blocking | TC-REV-005…006 | — |
| Reviewer note / stamp | TC-REV-008…009 | — |
| 50-day retention / purge | TC-RET-001…010 | integration retention |
| Audit action matrix | TC-AUD-001…013 | — |
| Full E2E smoke | TC-E2E-001…009 | `pytest` formulas + protocol flow + `test_users_admin_db.py` |

## Document index

| Doc | Path |
|-----|------|
| Test plan | [00_TEST_PLAN.md](00_TEST_PLAN.md) |
| Auth / RBAC | [01_AUTH_RBAC.md](01_AUTH_RBAC.md) |
| Admin | [02_ADMIN.md](02_ADMIN.md) |
| Reception | [03_RECEPTION_CTR.md](03_RECEPTION_CTR.md) |
| Analyst | [04_ANALYST.md](04_ANALYST.md) |
| Formulas | [05_FORMULAS.md](05_FORMULAS.md) |
| Reviewer | [06_REVIEWER.md](06_REVIEWER.md) |
| Retention / Audit | [07_RETENTION_AUDIT.md](07_RETENTION_AUDIT.md) |
| E2E / Regression | [08_E2E_REGRESSION.md](08_E2E_REGRESSION.md) |
