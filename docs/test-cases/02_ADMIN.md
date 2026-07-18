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

## TC-ADM-007 — Change user role

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Staff user exists; ≥2 active admins OR target is not last admin |
| **Steps** | Change `recv_qa` from reception → analyst. |
| **Expected** | Role updated; audit `user.set_role`. User next login has analyst access. |

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
| **Expected** | Shows who / when / action / entity; newest first; limit reasonable (≤500). After create/role/reset, corresponding `user.*` actions appear. |

---

## TC-ADM-016 — Non-admin cannot open Admin page

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as reception/analyst/reviewer |
| **Steps** | Open Admin page. |
| **Expected** | Access denied. |
