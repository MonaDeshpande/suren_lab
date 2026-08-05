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
| **Expected** | Login succeeds; home shows workspace links for all roles held; sidebar shows signed-in user and role list. |
| **Postconditions** | Session holds `user_id`, `username`, `roles`. |

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
| **Preconditions** | Admin has deactivated a staff user (TC-ADM-010). |
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

Users with **multiple roles** may open any workspace allowed for **any** of their roles (e.g. reception + analyst sees both Reception and Analyst links on home).

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
| **Expected** | Only Reviewer allowed among workspaces. Reception shows access denied. |

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
| **Expected** | `admin` sees all four; single-role staff see only their workspace(s); dual-role staff see union of allowed workspaces. |

---

## TC-RBAC-006 — Dual-role user (reception + analyst)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | RBAC |
| **Preconditions** | Admin assigned user `dual_qa` roles `reception` and `analyst` |
| **Steps** | Login as `dual_qa`. Open Reception and Analyst. Attempt Reviewer and Admin. |
| **Expected** | Reception and Analyst allowed; Reviewer and Admin denied. Home shows both workspace links. |

---

## Multi-user concurrent login

These cases verify that multiple staff can work at the same time on different browsers or PCs. Session state is per browser; all users share one PostgreSQL database.

---

## TC-AUTH-013 — Concurrent login (different users)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Multi-user |
| **Preconditions** | Two active users exist (e.g. `reception1` and `analyst1`) |
| **Steps** | 1. On PC A, sign in as reception user. 2. On PC B (or another browser), sign in as analyst user. 3. Both open their allowed workspaces. |
| **Expected** | Both sessions stay active. Each sidebar shows the correct signed-in user. Reception can open Reception; analyst can open Analyst. |

---

## TC-AUTH-014 — Same user, two browsers (no duplicate-login block)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Multi-user |
| **Preconditions** | Active analyst account |
| **Steps** | Sign in as the same analyst in Chrome and Edge (or two PCs). |
| **Expected** | Both logins succeed. No “already logged in elsewhere” message. |

---

## TC-AUTH-015 — Deactivated user session ends on next page load

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Multi-user |
| **Preconditions** | User logged in on PC A; admin deactivates that account |
| **Steps** | 1. Admin deactivates the user (TC-ADM-010). 2. On PC A, refresh or navigate to any workspace. |
| **Expected** | Login form shown; session cleared. User cannot continue without re-login (which fails while inactive). |

---

## TC-AUTH-016 — LAN access from another PC

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Multi-user |
| **Preconditions** | Host runs `run_app.bat`; `.streamlit/config.toml` binds `0.0.0.0` |
| **Steps** | From another PC on the LAN, open `http://<host-ip>:8501` and sign in. |
| **Expected** | App loads and login works. Only the host needs Docker Postgres; client uses browser only. |
