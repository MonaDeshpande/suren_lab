"""
services/users.py
-----------------
Admin CRUD for lab user accounts (create, list, role, activate, reset password).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from db.connection import get_db
from services.audit import log_from_user
from services.auth import ROLES, hash_password


@dataclass
class UserRow:
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def list_users() -> list[UserRow]:
    sql = """
        SELECT id, username, COALESCE(full_name, ''), role,
               is_active, must_change_password, created_at, updated_at
          FROM users
         ORDER BY username
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        UserRow(
            id=r[0],
            username=r[1],
            full_name=r[2],
            role=r[3],
            is_active=bool(r[4]),
            must_change_password=bool(r[5]),
            created_at=r[6],
            updated_at=r[7],
        )
        for r in rows
    ]


def count_active_admins(exclude_user_id: Optional[int] = None) -> int:
    sql = """
        SELECT COUNT(*) FROM users
         WHERE role = 'admin' AND is_active = TRUE
    """
    params: list = []
    if exclude_user_id is not None:
        sql += " AND id <> %s"
        params.append(exclude_user_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return int(row[0]) if row else 0


def create_user(
    username: str,
    temporary_password: str,
    role: str,
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
    if role not in ROLES:
        raise ValueError(f"Invalid role '{role}'. Use one of {ROLES}.")
    pw = temporary_password or ""
    if len(pw) < 6:
        raise ValueError("Temporary password must be at least 6 characters.")

    sql = """
        INSERT INTO users (
            username, password_hash, full_name, role,
            is_active, must_change_password
        ) VALUES (%s, %s, %s, %s, TRUE, TRUE)
        RETURNING id, username, COALESCE(full_name, ''), role,
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
                        role,
                    ),
                )
                row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ValueError(f"Username '{name}' is already taken.") from exc
        raise

    assert row is not None
    created = UserRow(
        id=row[0],
        username=row[1],
        full_name=row[2],
        role=row[3],
        is_active=bool(row[4]),
        must_change_password=bool(row[5]),
        created_at=row[6],
        updated_at=row[7],
    )
    log_from_user(
        actor,
        "user.create",
        "users",
        created.id,
        details=f"{created.username} role={created.role}",
    )
    return created


def set_role(
    user_id: int,
    role: str,
    actor_user_id: Optional[int] = None,
    actor=None,
) -> None:
    """Change a user's role. Protects the last active admin."""
    if role not in ROLES:
        raise ValueError(f"Invalid role '{role}'. Use one of {ROLES}.")

    if actor is not None and actor_user_id is None:
        actor_user_id = getattr(actor, "id", None)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, is_active FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found.")
            current_role, is_active = row[0], bool(row[1])
            if (
                current_role == "admin"
                and is_active
                and role != "admin"
                and count_active_admins(exclude_user_id=user_id) < 1
            ):
                raise ValueError(
                    "Cannot change role: this is the last active admin."
                )
            if (
                actor_user_id is not None
                and actor_user_id == user_id
                and current_role == "admin"
                and role != "admin"
                and count_active_admins(exclude_user_id=user_id) < 1
            ):
                raise ValueError("Cannot demote yourself: you are the only admin.")

            cur.execute(
                """
                UPDATE users
                   SET role = %s, updated_at = NOW()
                 WHERE id = %s
                """,
                (role, user_id),
            )
    log_from_user(
        actor,
        "user.set_role",
        "users",
        user_id,
        details=f"role={role}",
    )


def set_active(user_id: int, is_active: bool, actor=None) -> None:
    """Activate or deactivate a user. Cannot deactivate the last active admin."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, is_active FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found.")
            current_role, currently_active = row[0], bool(row[1])
            if (
                currently_active
                and not is_active
                and current_role == "admin"
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
