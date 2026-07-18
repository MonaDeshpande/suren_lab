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
| **Steps** | Run `pytest tests/unit/test_formulas.py -q` |
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

## Critical regression checklist (manual tick)

- [ ] Login admin works
- [ ] Create staff + forced password change
- [ ] CTR save + sample code format
- [ ] PDF CTR download
- [ ] Analyst moisture + dry-basis ash
- [ ] Auto `in_progress`
- [ ] Protocol generate
- [ ] Final report → `reported`
- [ ] Wrong-role page denied
- [ ] Last admin cannot deactivate self (sole admin)
- [ ] `pytest -q` unit suite passes

---

## Suggested release sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| QA | | | Pass / Fail |
| Lab lead | | | |
| Dev | | | |
