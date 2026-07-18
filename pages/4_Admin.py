"""
pages/4_Admin.py
----------------
Admin workspace: register users, assign/change roles, reset passwords,
activate / deactivate accounts, view recent audit log.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db.connection import test_connection  # noqa: E402
from services.audit import list_recent  # noqa: E402
from services.auth import ROLES, get_session_user  # noqa: E402
from services.users import (  # noqa: E402
    create_user,
    list_users,
    reset_password,
    set_active,
    set_role,
)
from ui.auth import require_role  # noqa: E402
from ui.components import (  # noqa: E402
    inject_styles,
    render_db_status,
    render_hero,
    render_section_title,
)

st.set_page_config(
    page_title="S Testing Laboratory — Admin",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded",
)

_STAFF_ROLES = ("reception", "analyst", "reviewer", "admin")


def main() -> None:
    require_role("admin")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Admin — Users & roles",
        subtitle=(
            "Register staff with a temporary password. They must change it "
            "at the desk on first login. Assign roles: "
            "<b>reception</b>, <b>analyst</b>, <b>reviewer</b> (or another admin)."
        ),
        badge="User management",
    )

    ok, msg = test_connection()
    render_db_status(ok, msg)
    st.write("")
    if not ok:
        st.error("Database not connected.")
        st.stop()

    # ----- Create user -----
    render_section_title("1. Register new user")
    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        with c1:
            username = st.text_input("Username", placeholder="e.g. priya.r")
            full_name = st.text_input("Full name", placeholder="Optional")
        with c2:
            role = st.selectbox("Role", list(_STAFF_ROLES), index=0)
            temp_password = st.text_input(
                "Temporary password",
                type="password",
                help="User must change this on first login.",
            )
        submitted = st.form_submit_button("Create user", type="primary")

    if submitted:
        try:
            user = create_user(
                username=username,
                temporary_password=temp_password,
                role=role,
                full_name=full_name,
                actor=actor,
            )
            st.success(
                f"Created **{user.username}** as **{user.role}**. "
                "They must change the temporary password on first login."
            )
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Create failed: {exc}")

    # ----- Manage users -----
    st.divider()
    render_section_title("2. Manage users")
    users = list_users()
    if not users:
        st.info("No users found. Run `python scripts/seed_admin.py`.")
    else:
        st.dataframe(
            [
                {
                    "ID": u.id,
                    "Username": u.username,
                    "Name": u.full_name or "—",
                    "Role": u.role,
                    "Active": "Yes" if u.is_active else "No",
                    "Must change password": "Yes" if u.must_change_password else "No",
                }
                for u in users
            ],
            use_container_width=True,
            hide_index=True,
        )

        by_id = {u.id: u for u in users}
        pick_id = st.selectbox(
            "Select user to manage",
            options=list(by_id.keys()),
            format_func=lambda i: f"{by_id[i].username} ({by_id[i].role})",
            key="admin_manage_user",
        )
        target = by_id[pick_id]

        st.markdown(
            f"**{target.username}** — role `{target.role}`, "
            f"{'active' if target.is_active else 'inactive'}"
        )

        m1, m2, m3 = st.columns(3)

        with m1:
            st.markdown("##### Change role")
            new_role = st.selectbox(
                "New role",
                list(ROLES),
                index=list(ROLES).index(target.role)
                if target.role in ROLES
                else 0,
                key="admin_new_role",
            )
            if st.button("Update role", key="admin_btn_role"):
                try:
                    set_role(
                        target.id,
                        new_role,
                        actor_user_id=actor.id if actor else None,
                        actor=actor,
                    )
                    st.success(f"Role set to **{new_role}**.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        with m2:
            st.markdown("##### Activate / deactivate")
            if target.is_active:
                if st.button("Deactivate user", key="admin_btn_deact"):
                    try:
                        set_active(target.id, False, actor=actor)
                        st.success("User deactivated.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            else:
                if st.button("Activate user", key="admin_btn_act"):
                    try:
                        set_active(target.id, True, actor=actor)
                        st.success("User activated.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

        with m3:
            st.markdown("##### Reset password")
            new_temp = st.text_input(
                "New temporary password",
                type="password",
                key="admin_reset_pw",
            )
            if st.button("Reset password", key="admin_btn_reset"):
                try:
                    reset_password(target.id, new_temp, actor=actor)
                    st.success(
                        "Password reset. User must change it on next login."
                    )
                except ValueError as exc:
                    st.error(str(exc))

    # ----- Audit log -----
    st.divider()
    render_section_title(
        "3. Audit log",
        "Who did what, with date/time (newest first).",
    )
    audit_rows = list_recent(limit=100)
    if not audit_rows:
        st.info(
            "No audit entries yet (or run "
            "`docker exec -i sls_lab_db psql -U sls_user -d sls_lab "
            "< scripts/migrate_audit.sql`)."
        )
    else:
        st.dataframe(
            [
                {
                    "When": (
                        r.occurred_at.strftime("%Y-%m-%d %H:%M:%S")
                        if r.occurred_at
                        else "—"
                    ),
                    "Who": r.user_name,
                    "Action": r.action,
                    "Table": r.entity_table,
                    "Record": r.entity_id or "—",
                    "Details": r.details or "—",
                }
                for r in audit_rows
            ],
            use_container_width=True,
            hide_index=True,
        )


main()
