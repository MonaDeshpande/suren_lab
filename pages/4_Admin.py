"""
pages/4_Admin.py
----------------
Admin workspace: register users, assign/change roles, reset passwords,
activate / deactivate accounts, browse formula catalog, view audit log.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db.connection import test_connection  # noqa: E402
from services.audit import list_recent  # noqa: E402
from services.versions import list_versions  # noqa: E402
from services.auth import MAX_ROLES_PER_USER, ROLES, get_session_user, roles_display  # noqa: E402
from services.protocols.test_catalog import (  # noqa: E402
    SAMPLE_CATEGORIES,
    TEST_CATALOG,
)
from services.users import (  # noqa: E402
    create_user,
    list_users,
    reset_password,
    set_active,
    set_roles,
)
from ui.auth import require_page_access  # noqa: E402
from ui.custom_formulas_panel import render_custom_formulas_panel  # noqa: E402
from ui.catalog_specs_panel import render_catalog_specs_panel  # noqa: E402
from ui.db_browser_panel import render_db_browser_panel  # noqa: E402
from ui.report_settings_panel import render_report_settings_panel  # noqa: E402
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
    require_page_access("admin")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Admin — Users, formulas, audit, versions & database",
        subtitle=(
            "Register staff with a temporary password. They must change it "
            "at the desk on first login. Assign up to "
            f"<b>{MAX_ROLES_PER_USER} roles</b> per user "
            "(e.g. reception + analyst). Browse version history for "
            "customer and request edits. Use the database explorer to "
            "view all tables and activate or deactivate any row."
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
            selected_roles = st.multiselect(
                "Role(s)",
                list(_STAFF_ROLES),
                default=["reception"],
                help=(
                    f"Select 1–{MAX_ROLES_PER_USER} roles. "
                    "Admin cannot be combined with other roles."
                ),
            )
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
                roles=selected_roles,
                full_name=full_name,
                actor=actor,
            )
            st.success(
                f"Created **{user.username}** with roles "
                f"**{roles_display(user.roles)}**. "
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
                    "Roles": roles_display(u.roles),
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
            format_func=lambda i: (
                f"{by_id[i].username} ({roles_display(by_id[i].roles)})"
            ),
            key="admin_manage_user",
        )
        target = by_id[pick_id]

        st.markdown(
            f"**{target.username}** — roles `{roles_display(target.roles)}`, "
            f"{'active' if target.is_active else 'inactive'}"
        )

        m1, m2, m3 = st.columns(3)

        with m1:
            st.markdown("##### Change roles")
            default_roles = list(target.roles) if target.roles else ["reception"]
            new_roles = st.multiselect(
                "New role(s)",
                list(ROLES),
                default=default_roles,
                key="admin_new_roles",
                help=(
                    f"1–{MAX_ROLES_PER_USER} roles; admin is exclusive."
                ),
            )
            if st.button("Update roles", key="admin_btn_role"):
                try:
                    set_roles(
                        target.id,
                        new_roles,
                        actor_user_id=actor.id if actor else None,
                        actor=actor,
                    )
                    st.success(f"Roles set to **{roles_display(tuple(new_roles))}**.")
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

    # ----- Catalog specs (methods & limits) -----
    st.divider()
    render_section_title("3. Test catalog (methods & limits)")
    render_catalog_specs_panel(actor)

    # ----- Custom formulas (Admin CRUD) -----
    st.divider()
    render_section_title("4. Custom formulas")
    render_custom_formulas_panel(actor)

    # ----- Built-in formulas catalog (read-only from code) -----
    with st.expander("Built-in formula catalog (worksheet definitions)", expanded=False):
        st.caption(
            "Worksheet formulas and inputs live in `services/protocols/test_catalog.py`. "
            "Method, limits, and units are edited in section 3 above."
        )
        catalog_rows = []
        for test in TEST_CATALOG.values():
            cat_labels = ", ".join(
                SAMPLE_CATEGORIES.get(c, c) for c in (test.categories or [])
            )
            input_labels = "; ".join(
                f"{f.label}" + (f" ({f.unit})" if f.unit else "")
                for f in test.inputs
            )
            catalog_rows.append(
                {
                    "Key": test.key,
                    "Test": test.name,
                    "Method": test.method,
                    "Unit": test.unit or "—",
                    "Categories": cat_labels or "—",
                    "Formula": test.formula_display,
                    "Inputs": input_labels or "—",
                }
            )
        st.dataframe(
            catalog_rows,
            use_container_width=True,
            hide_index=True,
        )
        for test in TEST_CATALOG.values():
            with st.expander(f"{test.name} (`{test.key}`)", expanded=False):
                st.markdown(f"**Method:** {test.method}")
                st.markdown(f"**Unit:** {test.unit or '—'}")
                st.markdown(
                    "**Categories:** "
                    + ", ".join(
                        SAMPLE_CATEGORIES.get(c, c) for c in (test.categories or [])
                    )
                )
                st.info(f"**Formula:** {test.formula_display}")
                if test.inputs:
                    st.markdown("**Worksheet inputs**")
                    st.dataframe(
                        [
                            {
                                "Field key": f.key,
                                "Label": f.label,
                                "Unit": f.unit or "—",
                                "Required": "Yes" if f.required else "No",
                                "Type": f.field_type,
                            }
                            for f in test.inputs
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

    # ----- Audit log -----
    st.divider()
    render_section_title(
        "4. Audit log",
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
                    "Edit reason": r.edit_reason or "—",
                }
                for r in audit_rows
            ],
            use_container_width=True,
            hide_index=True,
        )

    # ----- Version history -----
    st.divider()
    render_section_title(
        "5. Version history",
        "Immutable snapshots before customer or request edits (newest first).",
    )
    vf1, vf2, vf3 = st.columns([2, 2, 1])
    with vf1:
        entity_filter = st.selectbox(
            "Entity type",
            options=["All", "customers", "test_requests"],
            key="version_entity_filter",
        )
    with vf2:
        entity_id_filter = st.text_input(
            "Entity ID (optional)",
            key="version_entity_id",
            placeholder="e.g. 42",
        )
    with vf3:
        version_limit = st.number_input(
            "Limit",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
            key="version_limit",
        )

    version_rows = list_versions(
        entity_table=None if entity_filter == "All" else entity_filter,
        entity_id=entity_id_filter.strip() or None,
        limit=int(version_limit),
    )
    if not version_rows:
        st.info(
            "No version snapshots yet (or run "
            "`docker exec -i sls_lab_db psql -U sls_user -d sls_lab "
            "< scripts/migrate_versions.sql`)."
        )
    else:
        st.dataframe(
            [
                {
                    "When": (
                        v.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        if v.created_at
                        else "—"
                    ),
                    "Entity": v.entity_table,
                    "Record": v.entity_id,
                    "Version": v.version_no,
                    "Edited by": v.user_name,
                    "Reason": (
                        (v.edit_reason[:80] + "…")
                        if len(v.edit_reason) > 80
                        else v.edit_reason
                    ),
                }
                for v in version_rows
            ],
            use_container_width=True,
            hide_index=True,
        )
        for v in version_rows[:20]:
            with st.expander(
                f"v{v.version_no} — {v.entity_table} #{v.entity_id} "
                f"({v.user_name})",
                expanded=False,
            ):
                st.markdown(f"**Edit reason:** {v.edit_reason}")
                st.json(v.snapshot())

    render_report_settings_panel(actor)

    st.divider()
    render_db_browser_panel(actor)


main()
