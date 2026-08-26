"""
services/users.py
-----------------
Admin CRUD for lab user accounts (create, list, roles, activate, reset password).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from db.connection import get_db
from services.audit import log_from_user
from services.auth import MAX_ROLES_PER_USER, ROLES, hash_password, roles_display


@dataclass
class UserRow:
    id: int
    username: str
    full_name: str
    roles: tuple[str, ...]
    is_active: bool
    must_change_password: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def role(self) -> str:
        """Backward-compatible primary role label."""
        return roles_display(self.roles) if self.roles else ""


def validate_roles(roles: list[str]) -> tuple[str, ...]:
    """
    Normalize and validate role assignment (1–2 roles; admin is exclusive).

    Raises
    ------
    ValueError
    """
    normalized: list[str] = []
    for r in roles or []:
        key = (r or "").strip().lower()
        if not key:
            continue
        if key not in ROLES:
            raise ValueError(f"Invalid role '{key}'. Use one of {ROLES}.")
        if key not in normalized:
            normalized.append(key)

    if not normalized:
        raise ValueError("At least one role is required.")
    if len(normalized) > MAX_ROLES_PER_USER:
        raise ValueError(
            f"A user may have at most {MAX_ROLES_PER_USER} roles."
        )
    if "admin" in normalized and len(normalized) > 1:
        raise ValueError("Admin role cannot be combined with other roles.")
    return tuple(sorted(normalized, key=lambda r: ROLES.index(r)))


def _fetch_roles_map(user_ids: list[int]) -> dict[int, tuple[str, ...]]:
    if not user_ids:
        return {}
    sql = """
        SELECT user_id, role
          FROM user_roles
         WHERE user_id = ANY(%s)
         ORDER BY user_id, role
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_ids,))
            rows = cur.fetchall()
    by_user: dict[int, list[str]] = {}
    for uid, role in rows:
        by_user.setdefault(uid, []).append(role)
    return {uid: tuple(rlist) for uid, rlist in by_user.items()}


def _user_row_from_db(row: tuple, roles: tuple[str, ...]) -> UserRow:
    return UserRow(
        id=row[0],
        username=row[1],
        full_name=row[2],
        roles=roles,
        is_active=bool(row[3]),
        must_change_password=bool(row[4]),
        created_at=row[5],
        updated_at=row[6],
    )


def list_users() -> list[UserRow]:
    sql = """
        SELECT id, username, COALESCE(full_name, ''),
               is_active, must_change_password, created_at, updated_at
          FROM users
         ORDER BY username
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    ids = [r[0] for r in rows]
    roles_map = _fetch_roles_map(ids)
    return [
        _user_row_from_db(r, roles_map.get(r[0], ()))
        for r in rows
    ]


def get_user_roles(user_id: int) -> tuple[str, ...]:
    roles_map = _fetch_roles_map([user_id])
    return roles_map.get(user_id, ())


def user_has_role(user_id: int, role: str) -> bool:
    return role in get_user_roles(user_id)


def analyst_display_label(user: UserRow) -> str:
    """Friendly label for analyst pickers."""
    name = analyst_full_name(user)
    return f"{name} ({user.username})"


def analyst_full_name(user: UserRow) -> str:
    """Analyst display name without username suffix (protocol / reports)."""
    return (user.full_name or "").strip() or user.username


def list_active_analysts() -> list[UserRow]:
    """Active users with role 'analyst' (includes dual-role users)."""
    sql = """
        SELECT u.id, u.username, COALESCE(u.full_name, ''),
               u.is_active, u.must_change_password, u.created_at, u.updated_at
          FROM users u
          JOIN user_roles ur ON ur.user_id = u.id
         WHERE ur.role = 'analyst' AND u.is_active = TRUE
         ORDER BY COALESCE(u.full_name, u.username), u.username
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    ids = [r[0] for r in rows]
    roles_map = _fetch_roles_map(ids)
    return [
        _user_row_from_db(r, roles_map.get(r[0], ()))
        for r in rows
    ]


def assert_valid_analyst_assignee(user_id: int) -> None:
    """Raise ValueError when user_id is not an active analyst."""
    if user_id is None:
        raise ValueError("Analyst assignment is required.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.is_active
                  FROM users u
                  JOIN user_roles ur ON ur.user_id = u.id
                 WHERE u.id = %s AND ur.role = 'analyst'
                 LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError("Assigned analyst not found or does not have analyst role.")
    if not bool(row[0]):
        raise ValueError("Assigned analyst account is inactive.")


def count_active_admins(exclude_user_id: Optional[int] = None) -> int:
    sql = """
        SELECT COUNT(DISTINCT u.id)
          FROM users u
          JOIN user_roles ur ON ur.user_id = u.id
         WHERE ur.role = 'admin' AND u.is_active = TRUE
    """
    params: list = []
    if exclude_user_id is not None:
        sql += " AND u.id <> %s"
        params.append(exclude_user_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return int(row[0]) if row else 0


def _replace_user_roles(cur, user_id: int, roles: tuple[str, ...]) -> None:
    cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
    for role in roles:
        cur.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (%s, %s)",
            (user_id, role),
        )


def create_user(
    username: str,
    temporary_password: str,
    roles: list[str],
    full_name: str = "",
    actor=None,
) -> UserRow:
    """
    Register a new user. New accounts must change password on first login.

    Raises
    ------
    ValueError
        On validation failure or duplicate username.
    """
    name = (username or "").strip().lower()
    if not name:
        raise ValueError("Username is required.")
    if " " in name:
        raise ValueError("Username cannot contain spaces.")
    if len(name) < 3:
        raise ValueError("Username must be at least 3 characters.")
    role_tuple = validate_roles(roles)
    pw = temporary_password or ""
    if len(pw) < 6:
        raise ValueError("Temporary password must be at least 6 characters.")

    sql = """
        INSERT INTO users (
            username, password_hash, full_name,
            is_active, must_change_password
        ) VALUES (%s, %s, %s, TRUE, TRUE)
        RETURNING id, username, COALESCE(full_name, ''),
                  is_active, must_change_password, created_at, updated_at
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        name,
                        hash_password(pw),
                        (full_name or "").strip(),
                    ),
                )
                row = cur.fetchone()
                assert row is not None
                _replace_user_roles(cur, row[0], role_tuple)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ValueError(f"Username '{name}' is already taken.") from exc
        raise

    created = _user_row_from_db(row, role_tuple)
    log_from_user(
        actor,
        "user.create",
        "users",
        created.id,
        details=f"{created.username} roles={roles_display(created.roles)}",
    )
    return created


def set_roles(
    user_id: int,
    roles: list[str],
    actor_user_id: Optional[int] = None,
    actor=None,
) -> None:
    """Change a user's roles. Protects the last active admin."""
    role_tuple = validate_roles(roles)

    if actor is not None and actor_user_id is None:
        actor_user_id = getattr(actor, "id", None)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_active FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found.")
            is_active = bool(row[0])

            cur.execute(
                "SELECT role FROM user_roles WHERE user_id = %s",
                (user_id,),
            )
            current_roles = {r[0] for r in cur.fetchall()}
            losing_admin = (
                "admin" in current_roles
                and "admin" not in role_tuple
            )
            if losing_admin and is_active and count_active_admins(
                exclude_user_id=user_id
            ) < 1:
                raise ValueError(
                    "Cannot change roles: this is the last active admin."
                )
            if (
                actor_user_id is not None
                and actor_user_id == user_id
                and losing_admin
                and count_active_admins(exclude_user_id=user_id) < 1
            ):
                raise ValueError("Cannot demote yourself: you are the only admin.")

            _replace_user_roles(cur, user_id, role_tuple)
            cur.execute(
                "UPDATE users SET updated_at = NOW() WHERE id = %s",
                (user_id,),
            )
    log_from_user(
        actor,
        "user.set_roles",
        "users",
        user_id,
        details=f"roles={roles_display(role_tuple)}",
    )


def set_role(
    user_id: int,
    role: str,
    actor_user_id: Optional[int] = None,
    actor=None,
) -> None:
    """Backward-compatible single-role setter."""
    set_roles(user_id, [role], actor_user_id=actor_user_id, actor=actor)


def set_active(user_id: int, is_active: bool, actor=None) -> None:
    """Activate or deactivate a user. Cannot deactivate the last active admin."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_active FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found.")
            currently_active = bool(row[0])
            if (
                currently_active
                and not is_active
                and user_has_role(user_id, "admin")
                and count_active_admins(exclude_user_id=user_id) < 1
            ):
                raise ValueError(
                    "Cannot deactivate the last active admin."
                )
            cur.execute(
                """
                UPDATE users
                   SET is_active = %s, updated_at = NOW()
                 WHERE id = %s
                """,
                (is_active, user_id),
            )
    log_from_user(
        actor,
        "user.set_active",
        "users",
        user_id,
        details=f"is_active={is_active}",
    )


def reset_password(user_id: int, temporary_password: str, actor=None) -> None:
    """Set a temporary password and force change on next login."""
    pw = temporary_password or ""
    if len(pw) < 6:
        raise ValueError("Temporary password must be at least 6 characters.")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cur.fetchone():
                raise ValueError("User not found.")
            cur.execute(
                """
                UPDATE users
                   SET password_hash = %s,
                       must_change_password = TRUE,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (hash_password(pw), user_id),
            )
    log_from_user(
        actor,
        "user.reset_password",
        "users",
        user_id,
    )
