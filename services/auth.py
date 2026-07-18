"""
services/auth.py
----------------
Password hashing, login, session helpers, and default-admin bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import bcrypt
import streamlit as st

from db.connection import get_db

ROLES = ("admin", "reception", "analyst", "reviewer")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin@123"

_SESSION_KEYS = (
    "user_id",
    "username",
    "role",
    "full_name",
    "must_change_password",
)


@dataclass
class AuthUser:
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool


def hash_password(plain: str) -> str:
    """Return a bcrypt hash string for storage."""
    return bcrypt.hashpw(
        (plain or "").encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """Check plain password against stored bcrypt hash."""
    if not plain or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def _row_to_user(row: tuple) -> AuthUser:
    return AuthUser(
        id=row[0],
        username=row[1],
        full_name=row[2] or "",
        role=row[3],
        is_active=bool(row[4]),
        must_change_password=bool(row[5]),
    )


def get_user_by_username(username: str) -> Optional[AuthUser]:
    name = (username or "").strip().lower()
    if not name:
        return None
    sql = """
        SELECT id, username, COALESCE(full_name, ''), role,
               is_active, must_change_password
          FROM users
         WHERE LOWER(username) = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name,))
            row = cur.fetchone()
    return _row_to_user(row) if row else None


def get_user_by_id(user_id: int) -> Optional[AuthUser]:
    sql = """
        SELECT id, username, COALESCE(full_name, ''), role,
               is_active, must_change_password
          FROM users
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
    return _row_to_user(row) if row else None


def _password_hash_for(username: str) -> Optional[str]:
    name = (username or "").strip().lower()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE LOWER(username) = %s",
                (name,),
            )
            row = cur.fetchone()
    return row[0] if row else None


def authenticate(username: str, password: str) -> Optional[AuthUser]:
    """
    Verify credentials. Returns AuthUser if valid and active, else None.
    """
    user = get_user_by_username(username)
    if user is None or not user.is_active:
        return None
    stored = _password_hash_for(user.username)
    if stored is None or not verify_password(password, stored):
        return None
    return user


def set_session_user(user: AuthUser) -> None:
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    st.session_state["role"] = user.role
    st.session_state["full_name"] = user.full_name
    st.session_state["must_change_password"] = user.must_change_password


def clear_session_user() -> None:
    for key in _SESSION_KEYS:
        st.session_state.pop(key, None)


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def get_session_user() -> Optional[AuthUser]:
    uid = st.session_state.get("user_id")
    if not uid:
        return None
    return AuthUser(
        id=int(uid),
        username=str(st.session_state.get("username") or ""),
        full_name=str(st.session_state.get("full_name") or ""),
        role=str(st.session_state.get("role") or ""),
        is_active=True,
        must_change_password=bool(
            st.session_state.get("must_change_password", False)
        ),
    )


def refresh_session_from_db() -> Optional[AuthUser]:
    """Reload current user from DB into session (e.g. after password change)."""
    uid = st.session_state.get("user_id")
    if not uid:
        return None
    user = get_user_by_id(int(uid))
    if user is None or not user.is_active:
        clear_session_user()
        return None
    set_session_user(user)
    return user


def change_password(
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    """
    Change password for user_id after verifying current_password.
    Clears must_change_password flag.

    Raises
    ------
    ValueError
        On validation / auth failure.
    """
    new_pw = (new_password or "").strip()
    if len(new_pw) < 6:
        raise ValueError("New password must be at least 6 characters.")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE id = %s AND is_active",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found or inactive.")
            if not verify_password(current_password, row[0]):
                raise ValueError("Current password is incorrect.")
            cur.execute(
                """
                UPDATE users
                   SET password_hash = %s,
                       must_change_password = FALSE,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (hash_password(new_pw), user_id),
            )

    if st.session_state.get("user_id") == user_id:
        st.session_state["must_change_password"] = False


def ensure_default_admin() -> bool:
    """
    Create admin / Admin@123 if no admin user exists yet.

    Returns
    -------
    bool
        True if a new admin was created.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE LOWER(username) = %s",
                (DEFAULT_ADMIN_USERNAME,),
            )
            if cur.fetchone():
                return False
            cur.execute(
                """
                INSERT INTO users (
                    username, password_hash, full_name, role,
                    is_active, must_change_password
                ) VALUES (%s, %s, %s, %s, TRUE, FALSE)
                """,
                (
                    DEFAULT_ADMIN_USERNAME,
                    hash_password(DEFAULT_ADMIN_PASSWORD),
                    "Administrator",
                    "admin",
                ),
            )
    return True
