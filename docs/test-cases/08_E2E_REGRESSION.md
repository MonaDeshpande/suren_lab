# End-to-End & Regression Pack

**Module:** Full workflow smoke + release checklist  
**Run:** After major changes and before every release

---

## TC-E2E-001 — Full happy path (Admin → Reception → Analyst → Reviewer)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Preconditions** | Fresh/test DB; admin seeded |

### Steps

1. **Admin:** Create `e2e_recv`, `e2e_anl`, `e2e_rev` with temp passwords; assign roles.
2. **Each staff:** First login → forced password change → success.
3. **Reception (`e2e_recv`):** Save CTR with 1 sample, tests Moisture + Appearance + Total ash; note `sample_code`.
4. Download CTR PDF; confirm sample code on screen.
5. **Analyst (`e2e_anl`):** Open sample; save protocol header; save Appearance; save Moisture (W1=10.5, W=5, W2=10.2 → 6.0); save Total ash with moisture context; set status `completed`; generate protocol PDF.
6. **Reviewer (`e2e_rev`):** Open sample; confirm data; Generate Final Report; download PDF; confirm status `reported`.
7. **Admin:** Confirm audit entries for request.save, result.save, report.final, etc.

### Expected

- No blocking errors.
- Sample progresses `pending` → `in_progress` → `completed` → `reported`.
- All three documents (CTR / Protocol / Final) downloadable.
- Customer record reusable for a second CTR.

---

## TC-E2E-002 — Multi-sample handoff

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Regression |
| **Steps** | Reception saves 2 samples; analyst completes both; reviewer reports both. |
| **Expected** | Independent codes and statuses; no cross-contamination of results. |

---

## TC-E2E-003 — RBAC smoke across roles

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Steps** | For each role, attempt all four workspace pages. |
| **Expected** | Matches matrix in [01_AUTH_RBAC.md](01_AUTH_RBAC.md). |

---

## TC-E2E-004 — Last-admin protection still holds

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Regression |
| **Steps** | With single active admin, attempt demote + deactivate. |
| **Expected** | Both blocked. |

---

## TC-E2E-005 — Formula regression spot-check

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Steps** | Run `pytest tests/unit/test_formulas.py -q` (Jaggery + Water + Basic Nutrition) |
| **Expected** | All green. |

---

## TC-E2E-006 — Inactive user blocked mid-lifecycle

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Regression |
| **Steps** | Admin deactivates analyst; analyst attempts login. |
| **Expected** | Login fails. |

---

## TC-E2E-007 — Water sample full protocol flow

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Preconditions** | Fresh/test DB |

### Steps

1. **Reception:** Save CTR with 1 **Water** sample (all 11 tests auto-assigned).
2. **Analyst:** Open sample; save protocol header; save at least pH + TDS results; generate protocol DOCX.
3. Open DOCX: confirm page-1 Method column shows IS 3025 references unchanged; Result column shows saved values.
4. Print/download; confirm signature blocks blank; pen-sign offline.

### Expected

- Water template used (`Water protocol 2025.docx` structure).
- All 11 tests listed in analyst selector.
- See TC-ANL-020…025.

---

## TC-E2E-008 — Basic Nutrition food protocol flow

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Preconditions** | Fresh/test DB |

### Steps

1. **Reception:** Save CTR with 1 **Food** sample; select Basic Nutrition tests (e.g. Moisture `bn_moisture`, Protein `bn_protein`).
2. **Analyst:** Save header; enter worksheet readings; Calculate & save each test; generate protocol DOCX.
3. Open DOCX: confirm Basic Nutrition template layout; page-1 methods match reference; results filled.
4. Set status `completed`; **Reviewer** generates Final Report separately.

### Expected

- Basic Nutrition template used when any `bn_*` test selected.
- Results auto-calculated (analyst does not type final result manually).
- Protocol is internal lab document; customer report from Reviewer.

---

## TC-E2E-009 — Admin post-login user lifecycle

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Regression |
| **Preconditions** | DB up; default admin seeded (`admin` / `Admin@123`) |
| **Related** | TC-ADM-001…002, 007b, 008…012, 019…020; TC-AUTH-004, 006 |

### Steps

1. Login as `admin` / `Admin@123` → open **Admin**.
2. Create `recv_mgmt` (reception), `anl_mgmt` (analyst), `rev_mgmt` (reviewer) with temp passwords ≥6 chars.
3. Confirm all three appear in the user list as **active** with the expected roles.
4. Change `recv_mgmt` roles to **reception + analyst**; after forced password change, confirm dual workspace access.
5. Deactivate `anl_mgmt` → login with that user fails (TC-AUTH-004).
6. Reactivate `anl_mgmt` → login works again.
7. Reset password for `rev_mgmt` → next login requires forced password change (TC-AUTH-006 / TC-ADM-012).
8. With only one active admin, attempt to demote or deactivate that admin → both blocked (TC-ADM-008/009, TC-ADM-020).

### Expected

- Admin can create and manage all staff roles after login.
- Activate / deactivate / role change / reset password behave as above.
- Last active admin cannot remove themselves from admin capability.

---

## Critical regression checklist (manual tick)

- [ ] Login admin works
- [ ] Create staff + forced password change
- [ ] CTR save + sample code format
- [ ] PDF CTR download
- [ ] Analyst moisture + dry-basis ash
- [ ] Auto `in_progress`
- [ ] Protocol generate
- [ ] Admin user lifecycle: create / dual-role / deactivate / reactivate / reset (TC-E2E-009)
- [ ] Water sample: 11 tests + Water protocol DOCX (TC-E2E-007)
- [ ] Basic Nutrition food: bn_* tests + Nutrition protocol DOCX (TC-E2E-008)
- [ ] Final report → `reported`
- [ ] Wrong-role page denied
- [ ] Last admin cannot deactivate self (sole admin)
- [ ] `pytest -q` unit suite passes
- [ ] `pytest tests/integration/test_users_admin_db.py -q` (DB up)

---

## Suggested release sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| QA | | | Pass / Fail |
| Lab lead | | | |
| Dev | | | |
