# Auth & RBAC — Test Cases

**Module:** Authentication / Role-Based Access Control  
**Related code:** `services/auth.py`, `ui/auth.py`, `pages/*.py`, `app.py`

---

## TC-AUTH-001 — Successful login (admin)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | DB up; default admin seeded (`admin` / `Admin@123`) |
| **Steps** | 1. Open app home. 2. Enter username `admin`, password `Admin@123`. 3. Click **Sign in**. |
| **Expected** | Login succeeds; home shows workspace links for all four roles; sidebar shows signed-in user. |
| **Postconditions** | Session holds `user_id`, `username`, `role=admin`. |

---

## TC-AUTH-002 — Wrong password

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Valid username exists |
| **Steps** | 1. Enter valid username with incorrect password. 2. Sign in. |
| **Expected** | Error: `Invalid username or password, or account is inactive.` No session created. |

---

## TC-AUTH-003 — Unknown username

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Steps** | Sign in with username that does not exist. |
| **Expected** | Same generic invalid/inactive message (no user enumeration). |

---

## TC-AUTH-004 — Inactive user cannot login

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Preconditions** | Admin has deactivated a staff user (TC-ADM-006). |
| **Steps** | Attempt login with that user's credentials. |
| **Expected** | Login rejected with invalid/inactive message. |

---

## TC-AUTH-005 — Username case-insensitive

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Preconditions** | User `reception1` exists |
| **Steps** | Login with `Reception1` / `RECEPTION1` and correct password. |
| **Expected** | Login succeeds (lookup uses `LOWER(username)`). |

---

## TC-AUTH-006 — Forced password change on first login (staff)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | New user created with temp password; `must_change_password=TRUE` |
| **Steps** | 1. Login with temp credentials. 2. Observe forced-change screen. 3. Enter current temp password, new password (≥6 chars), matching confirm. 4. Save. |
| **Expected** | Success; user can reach home/workspaces. Flag cleared. |
| **Postconditions** | `must_change_password=FALSE` in DB. |

---

## TC-AUTH-007 — Forced change: password mismatch confirm

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Preconditions** | User with `must_change_password=TRUE` |
| **Steps** | Enter new password and different confirmation; submit. |
| **Expected** | Error: new password and confirmation do not match. Flag remains TRUE. |

---

## TC-AUTH-008 — Forced change: new password too short

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Preconditions** | User with `must_change_password=TRUE` |
| **Steps** | Set new password to 5 characters (matching confirm); submit. |
| **Expected** | Error: `New password must be at least 6 characters.` |

---

## TC-AUTH-009 — Forced change: wrong current password

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Steps** | Enter incorrect current password with valid new password (≥6). |
| **Expected** | Error: `Current password is incorrect.` |

---

## TC-AUTH-010 — Bootstrap admin skips forced change

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Preconditions** | Fresh seed; only default admin |
| **Steps** | Login as `admin` / `Admin@123`. |
| **Expected** | No forced password-change screen; home usable immediately. |

---

## TC-AUTH-011 — Logout

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Preconditions** | User logged in |
| **Steps** | Click **Log out** in sidebar. |
| **Expected** | Session cleared; login form shown. Protected pages inaccessible without re-login. |

---

## TC-AUTH-012 — Unauthenticated access blocked

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged out |
| **Steps** | Navigate directly to Reception / Analyst / Reviewer / Admin page URLs. |
| **Expected** | Login form shown; page content not available (`require_login`). |

---

## RBAC matrix

| Page | admin | reception | analyst | reviewer |
|------|-------|-----------|---------|----------|
| Home (`app.py`) | Allow | Allow | Allow | Allow |
| Reception | Allow | Allow | Deny | Deny |
| Analyst | Allow | Deny | Allow | Deny |
| Reviewer | Allow | Deny | Deny | Allow |
| Admin | Allow | Deny | Deny | Deny |

---

## TC-RBAC-001 — Reception role: allow Reception, deny others

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as `reception` |
| **Steps** | Open Reception (OK). Open Analyst, Reviewer, Admin. |
| **Expected** | Reception works. Others show `Access denied — your role cannot open this page.` with link home. |

---

## TC-RBAC-002 — Analyst role page gates

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as `analyst` |
| **Steps** | Open Analyst (OK). Open Reception, Reviewer, Admin. |
| **Expected** | Only Analyst allowed among workspaces. |

---

## TC-RBAC-003 — Reviewer role page gates

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as `reviewer` |
| **Steps** | Open Reviewer (OK). Open Reception, Analyst, Admin. |
| **Expected** | Only Reviewer allowed among workspaces. |

---

## TC-RBAC-004 — Admin can open all workspaces

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Logged in as `admin` |
| **Steps** | Open Reception, Analyst, Reviewer, Admin. |
| **Expected** | All pages load without access denied. |

---

## TC-RBAC-005 — Home links match role

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | RBAC |
| **Steps** | Login as each role; inspect home workspace links. |
| **Expected** | `admin` sees all four; other roles see only their workspace (+ home). |
