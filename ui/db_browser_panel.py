"""
ui/db_browser_panel.py
----------------------
Admin database explorer: browse tables, view rows, activate/deactivate.
"""

from __future__ import annotations

import streamlit as st

from services.db_admin import (
    count_rows,
    fetch_rows,
    get_row,
    list_tables,
    set_row_active,
    table_label,
)
from services.versions import list_versions
from ui.components import edit_reason_field, render_section_title, require_edit_reason


def _grouped_table_options() -> list[str]:
    tables = list_tables()
    by_group: dict[str, list[str]] = {}
    for t in tables:
        grp = t.get("group") or "Other"
        by_group.setdefault(grp, []).append(t["name"])
    options: list[str] = []
    for grp in ("Business", "Auth", "Audit", "Other"):
        for name in sorted(by_group.get(grp, [])):
            options.append(name)
    return options


def render_db_browser_panel(actor) -> None:
    """Render the admin database explorer section."""
    render_section_title(
        "6. Database explorer",
        "Browse all tables, view row data, and soft-delete (deactivate) or "
        "reactivate rows. Password hashes are never shown.",
    )

    table_options = _grouped_table_options()
    if not table_options:
        st.info("No database tables found.")
        return

    meta_by_name = {t["name"]: t for t in list_tables()}

    c1, c2, c3 = st.columns([3, 2, 1])
    with c1:
        selected_table = st.selectbox(
            "Table",
            options=table_options,
            format_func=lambda n: f"{meta_by_name[n]['group']} — {table_label(n)}",
            key="db_browser_table",
        )
    with c2:
        search = st.text_input(
            "Search",
            key="db_browser_search",
            placeholder="Filter rows…",
        )
    with c3:
        page_size = st.number_input(
            "Page size",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            key="db_browser_page_size",
        )

    meta = meta_by_name.get(selected_table, {})
    show_inactive = True
    if meta.get("has_is_active"):
        show_inactive = st.checkbox(
            "Show inactive rows",
            value=True,
            key="db_browser_show_inactive",
        )

    if "db_browser_page" not in st.session_state:
        st.session_state.db_browser_page = 0

    total = count_rows(
        selected_table,
        include_inactive=show_inactive,
        search=search.strip() or None,
    )
    page = int(st.session_state.db_browser_page)
    max_page = max(0, (total - 1) // int(page_size)) if total else 0
    if page > max_page:
        page = 0
        st.session_state.db_browser_page = 0

    rows = fetch_rows(
        selected_table,
        limit=int(page_size),
        offset=page * int(page_size),
        include_inactive=show_inactive,
        search=search.strip() or None,
    )

    st.caption(f"{total} row(s) in **{selected_table}**")
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No rows match the current filters.")

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("◀ Prev", disabled=page <= 0, key="db_browser_prev"):
            st.session_state.db_browser_page = max(0, page - 1)
            st.rerun()
    with nav2:
        st.markdown(f"<div style='text-align:center'>Page {page + 1} of {max_page + 1}</div>", unsafe_allow_html=True)
    with nav3:
        if st.button("Next ▶", disabled=page >= max_page, key="db_browser_next"):
            st.session_state.db_browser_page = page + 1
            st.rerun()

    if selected_table in ("audit_log", "entity_versions"):
        st.info(
            f"**{table_label(selected_table)}** is read-only — rows cannot be "
            "activated or deactivated."
        )
        return

    pk = meta.get("pk") or "id"
    st.divider()
    st.markdown("**Row actions**")

    pk_options = [str(r.get(pk)) for r in rows if r.get(pk) is not None]
    selected_pk = st.selectbox(
        f"Select row ({pk})",
        options=pk_options or ["—"],
        key="db_browser_selected_pk",
    )

    if selected_pk and selected_pk != "—":
        row_data = get_row(selected_table, selected_pk)
        if row_data:
            with st.expander(f"Row detail — {pk}={selected_pk}", expanded=False):
                st.json(row_data)

            version_rows = list_versions(
                entity_table=selected_table,
                entity_id=str(selected_pk),
                limit=20,
            )
            if version_rows:
                with st.expander("Version history for this row", expanded=False):
                    st.dataframe(
                        [
                            {
                                "Version": v.version_no,
                                "When": (
                                    v.created_at.strftime("%Y-%m-%d %H:%M:%S")
                                    if v.created_at
                                    else "—"
                                ),
                                "By": v.user_name,
                                "Reason": v.edit_reason,
                            }
                            for v in version_rows
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

        if meta.get("toggle"):
            reason = edit_reason_field(key="db_browser_edit_reason")
            deactivate_conflicts = False
            if meta.get("has_is_active") and row_data and not row_data.get("is_active"):
                deactivate_conflicts = st.checkbox(
                    "Deactivate conflicting active row when activating",
                    value=False,
                    key="db_browser_deactivate_conflicts",
                    help="Required when another active row shares the same business key.",
                )

            btn1, btn2 = st.columns(2)
            with btn1:
                if st.button(
                    "Deactivate row",
                    key="db_browser_deactivate",
                    disabled=row_data is not None and not row_data.get("is_active", True),
                ):
                    if not require_edit_reason(reason):
                        st.error("Edit reason is required (min 10 characters).")
                    else:
                        try:
                            set_row_active(
                                selected_table,
                                selected_pk,
                                False,
                                reason,
                                actor=actor,
                            )
                            st.success(f"Row {selected_pk} deactivated.")
                            st.rerun()
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
            with btn2:
                if st.button(
                    "Activate row",
                    key="db_browser_activate",
                    disabled=row_data is not None and bool(row_data.get("is_active")),
                ):
                    if not require_edit_reason(reason):
                        st.error("Edit reason is required (min 10 characters).")
                    else:
                        try:
                            set_row_active(
                                selected_table,
                                selected_pk,
                                True,
                                reason,
                                actor=actor,
                                deactivate_conflicts=deactivate_conflicts,
                            )
                            st.success(f"Row {selected_pk} activated.")
                            st.rerun()
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
        else:
            st.caption("This table does not support row activation toggles.")
