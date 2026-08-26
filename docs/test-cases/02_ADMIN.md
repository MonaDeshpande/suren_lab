# Admin — Test Cases

**Module:** User management & audit log viewer  
**Related code:** `pages/4_Admin.py`, `services/users.py`, `services/audit.py`  
**Access:** `admin` only

---

## TC-ADM-001 — Create staff user (reception)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as admin |
| **Steps** | 1. Open Admin. 2. Create user: username `recv_qa`, role `reception`, temp password `Temp@12`, full name optional. 3. Submit. |
| **Expected** | Success; user appears in list with role reception, active. |
| **Postconditions** | `must_change_password=TRUE`; audit `user.create` on `users`. |

---

## TC-ADM-002 — Create analyst and reviewer users

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Steps** | Create `analyst_qa` (analyst) and `review_qa` (reviewer) with valid temp passwords. |
| **Expected** | Both created; usable after forced password change. |

---

## TC-ADM-003 — Duplicate username rejected

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Username `recv_qa` exists |
| **Steps** | Create another user with same username (any case). |
| **Expected** | Error that username is already taken. |

---

## TC-ADM-004 — Username validation (spaces / length)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Steps** | Attempt create with: (a) empty username, (b) username with spaces, (c) 2-character username. |
| **Expected** | (a) Username required. (b) Cannot contain spaces. (c) Must be at least 3 characters. |

---

## TC-ADM-005 — Temporary password minimum length

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Steps** | Create user with temp password of 5 characters. |
| **Expected** | Error: temporary password must be at least 6 characters. |

---

## TC-ADM-006 — Invalid role rejected

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Notes** | UI only offers valid roles; service rejects invalid if called. |
| **Expected** | Role must be one of `admin`, `reception`, `analyst`, `reviewer`. |

---

## TC-ADM-007 — Change user roles

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Staff user exists; ≥2 active admins OR target is not last admin |
| **Steps** | Change `recv_qa` from reception → analyst (or assign reception + analyst). |
| **Expected** | Roles updated; audit `user.set_roles`. User next login has matching workspace access. |

---

## TC-ADM-007b — Assign two roles to one user

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Logged in as admin |
| **Steps** | Create or update user with roles `reception` and `analyst`. |
| **Expected** | Both roles stored; user can open Reception and Analyst. |

---

## TC-ADM-007c — Admin role cannot be combined

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Steps** | Attempt to assign `admin` + `reception` to one user. |
| **Expected** | Error: admin cannot be combined with other roles. |

---

## TC-ADM-007d — More than two roles rejected

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Steps** | Attempt to assign three non-admin roles. |
| **Expected** | Error: at most 2 roles per user. |

---

## TC-ADM-008 — Cannot demote last active admin

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Only one active admin in the system |
| **Steps** | Attempt to change that admin's role to `reception`. |
| **Expected** | Error: cannot change role — last active admin. |

---

## TC-ADM-009 — Cannot deactivate last active admin

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Only one active admin |
| **Steps** | Attempt to deactivate that admin. |
| **Expected** | Error: cannot deactivate the last active admin. |

---

## TC-ADM-010 — Deactivate staff user

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Active non-admin staff exists |
| **Steps** | Deactivate the user. |
| **Expected** | `is_active=FALSE`; audit `user.set_active`; login fails (TC-AUTH-004). |

---

## TC-ADM-010a — Deactivate reception user

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Active user with role `reception` exists |
| **Steps** | 1. Admin deactivates the reception user. 2. Attempt login with that user's credentials. |
| **Expected** | User list shows inactive; login rejected (TC-AUTH-004); Reception workspace inaccessible. |

---

## TC-ADM-010b — Deactivate analyst user

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Active user with role `analyst` exists |
| **Steps** | 1. Admin deactivates the analyst user. 2. Attempt login with that user's credentials. |
| **Expected** | User list shows inactive; login rejected (TC-AUTH-004); Analyst workspace inaccessible. |

---

## TC-ADM-010c — Deactivate reviewer user

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Active user with role `reviewer` exists |
| **Steps** | 1. Admin deactivates the reviewer user. 2. Attempt login with that user's credentials. |
| **Expected** | User list shows inactive; login rejected (TC-AUTH-004); Reviewer workspace inaccessible. |

---

## TC-ADM-011 — Reactivate user

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | User deactivated |
| **Steps** | Activate again. |
| **Expected** | User can login again; audit recorded. |

---

## TC-ADM-012 — Reset password

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | Staff user exists |
| **Steps** | Reset password to a new temp ≥6 chars. |
| **Expected** | Success; `must_change_password=TRUE`; audit `user.reset_password`. User must change password on next login. |

---

## TC-ADM-013 — Reset password too short

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Steps** | Reset with password length 5. |
| **Expected** | Validation error (min 6). |

---

## TC-ADM-014 — Promote second admin then demote first

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | 1. Create/promote another user to admin. 2. Demote or deactivate original bootstrap admin. |
| **Expected** | Allowed when another active admin remains. |

---

## TC-ADM-015 — Audit log visible (newest first)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Several admin actions performed |
| **Steps** | Open audit section on Admin page; review recent rows. |
| **Expected** | Shows who / when / action / entity; newest first; limit reasonable (≤500). After create/role/reset, corresponding `user.*` actions appear (`user.set_roles` for role changes). |

---

## TC-ADM-017 — Version history visible

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | At least one customer or request edit with reason |
| **Steps** | Open **Version history** on Admin page; filter by entity type / ID. |
| **Expected** | Shows version #, entity, editor, timestamp, reason; expander shows JSON snapshot of prior state. |

---

## TC-ADM-018 — Audit log shows edit reason

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Positive |
| **Preconditions** | Edit with reason performed |
| **Steps** | Open audit log after `customer.update` or `request.update`. |
| **Expected** | **Edit reason** column populated for that row. |

---

## TC-ADM-016 — Non-admin cannot open Admin page

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as reception/analyst/reviewer |
| **Steps** | Open Admin page. |
| **Expected** | Access denied. |

---

## TC-ADM-019 — Deactivate non-sole second admin

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | At least two active admins (e.g. after TC-ADM-014: bootstrap admin + second admin) |
| **Steps** | 1. Select the second admin. 2. Deactivate that user. |
| **Expected** | Second admin deactivated; first admin remains active and can still manage users. |

---

## TC-ADM-020 — Sole admin cannot self-demote or self-deactivate

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Logged in as the only active admin |
| **Steps** | 1. Attempt to change own roles away from `admin` (e.g. to `reception`). 2. Attempt to deactivate own account. |
| **Expected** | Both blocked with last-admin / self-demote errors; session remains admin and active. |

---

## TC-ADM-021 — Edit built-in test catalog (methods & limits)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Logged in as admin; `catalog_test_specs` seeded |
| **Steps** | 1. Open Admin → **Test catalog (methods & limits)**. 2. Filter Micro; select E. Coli. 3. Confirm caption shows **Version: vN (Latest)**. 4. Change method text; enter edit reason; **Save as new version**. 5. Re-open Analyst micro sample — confirm updated method caption. 6. Open **Version history** — prior version listed with user, time, reason. |
| **Expected** | Save archives prior row to `entity_versions` and bumps `current_version_no` on the live row. Grid shows `vN · Latest`. Analyst and Micro protocol/report read the latest method/limits from DB. `test_key` stays read-only. Water rows show Desirable/Permissible fields; Micro rows show Limits text. |
| **Automated** | `test_catalog_specs_db.py` |
