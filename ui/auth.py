"""
ui/auth.py
----------
Login form, logout, forced password change, and page role gates.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from services.auth import (
    AuthUser,
    authenticate,
    change_password,
    clear_session_user,
    ensure_default_admin,
    get_session_user,
    is_logged_in,
    refresh_session_from_db,
    set_session_user,
)


def render_logout_sidebar() -> None:
    """Show logged-in user + logout in the sidebar."""
    user = get_session_user()
    if user is None:
        return
    with st.sidebar:
        st.markdown("---")
        label = user.full_name or user.username
        st.caption(f"Signed in as **{label}** ({user.role})")
        if st.button("Log out", key="sidebar_logout", use_container_width=True):
            clear_session_user()
            st.rerun()


def render_login_form() -> None:
    """Full-page login. Ensures default admin exists when DB is reachable."""
    st.markdown("### Sign in")
    st.caption("Use the credentials provided by your administrator.")

    try:
        ensure_default_admin()
    except Exception:  # noqa: BLE001
        # DB may be down — login will fail with a clear error below
        pass

    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Sign in", type="primary")

    if not submitted:
        return

    try:
        user = authenticate(username, password)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Login failed: {exc}")
        return

    if user is None:
        st.error("Invalid username or password, or account is inactive.")
        return

    set_session_user(user)
    st.rerun()


def render_forced_password_change() -> None:
    """Block app use until the user sets a new password."""
    user = get_session_user()
    if user is None:
        return

    st.warning(
        "You must change your temporary password before continuing."
    )
    st.markdown("### Change password")

    with st.form("force_password_change"):
        current = st.text_input(
            "Current (temporary) password",
            type="password",
            autocomplete="current-password",
        )
        new_pw = st.text_input(
            "New password",
            type="password",
            autocomplete="new-password",
        )
        confirm = st.text_input(
            "Confirm new password",
            type="password",
            autocomplete="new-password",
        )
        submitted = st.form_submit_button("Save new password", type="primary")

    if not submitted:
        if st.button("Log out instead"):
            clear_session_user()
            st.rerun()
        return

    if new_pw != confirm:
        st.error("New password and confirmation do not match.")
        return

    try:
        change_password(user.id, current, new_pw)
        refresh_session_from_db()
        st.success("Password updated. You can use the app now.")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


def require_login() -> Optional[AuthUser]:
    """
    Ensure the user is logged in and has changed temp password.

    Returns AuthUser, or stops the page (login / change-password UI).
    """
    if not is_logged_in():
        render_login_form()
        st.stop()
        return None

    user = get_session_user()
    if user is None:
        clear_session_user()
        render_login_form()
        st.stop()
        return None

    if user.must_change_password:
        render_forced_password_change()
        st.stop()
        return None

    render_logout_sidebar()
    return user


def require_role(*roles: str) -> Optional[AuthUser]:
    """
    require_login() then ensure session role is one of ``roles``.

    Wrong role → access denied (no page content).
    """
    user = require_login()
    if user is None:
        return None

    allowed = {r.lower() for r in roles}
    if user.role.lower() not in allowed:
        st.error("Access denied — your role cannot open this page.")
        st.page_link("app.py", label="Back to Home", icon="🏠")
        st.stop()
        return None

    return user
