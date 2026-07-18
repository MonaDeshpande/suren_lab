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
| Create / validate users | TC-ADM-001…006 | — |
| Last-admin protection | TC-ADM-008…009, TC-E2E-004 | — |
| Activate / reset password | TC-ADM-010…013 | — |
| Audit viewer | TC-ADM-015, TC-AUD-* | — |
| CTR save happy / multi-sample | TC-REC-001…002, TC-E2E-001…002 | integration (optional) |
| CTR validation rules | TC-REC-003…009 | `test_validation.py` |
| Empty rows skipped | TC-REC-010 | `test_validation.py` |
| Customer GST upsert | TC-REC-011…012 | — |
| Sample code SLS-YYMMDD-NNNN | TC-REC-013…014 | integration `test_sample_code` |
| Shared catalog / expiry default | TC-REC-015…016 | — |
| CTR PDF / DOCX | TC-REC-017…018 | — |
| Analyst search / queue | TC-ANL-001…003 | — |
| Protocol header / results | TC-ANL-004…005 | — |
| Auto in_progress | TC-ANL-006 | integration |
| Worksheet errors | TC-ANL-007…010 | `test_formulas.py` |
| Catalog restrict / fallback | TC-ANL-011…012 | — |
| Protocol document | TC-ANL-015 | — |
| Status completed | TC-ANL-016 | integration |
| Appearance / moisture / ash / … | TC-FOR-001…024 | `test_formulas.py` |
| Reviewer preconditions | TC-REV-002…003 | — |
| Final report → reported | TC-REV-004, TC-E2E-001 | — |
| Status warnings non-blocking | TC-REV-005…006 | — |
| Reviewer note / stamp | TC-REV-008…009 | — |
| 10-day retention / purge | TC-RET-001…010 | integration retention |
| Audit action matrix | TC-AUD-001…013 | — |
| Full E2E smoke | TC-E2E-001…006 | `pytest` formulas regression |

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
