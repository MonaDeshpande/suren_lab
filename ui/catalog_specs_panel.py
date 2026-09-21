"""
ui/catalog_specs_panel.py
-------------------------
Admin UI for editing built-in catalog test method, limits, and units.
"""

from __future__ import annotations

import streamlit as st

from services.catalog_specs import list_all_specs, list_spec_versions, update_spec
from services.protocols.test_catalog import SAMPLE_CATEGORIES
from ui.components import edit_reason_field, render_section_title, require_edit_reason


def _version_summary(snapshot: dict) -> str:
    method = (snapshot.get("method_of_analysis") or "").strip()
    limits = snapshot.get("limits_text") or ""
    if not limits:
        parts = [
            snapshot.get("limits_desirable") or "",
            snapshot.get("limits_permissible") or "",
        ]
        limits = " / ".join(p for p in parts if p)
    bits = []
    if method:
        bits.append(f"Method: {method[:60]}")
    if limits:
        bits.append(f"Limits: {limits[:60]}")
    return " · ".join(bits) if bits else "—"


def render_catalog_specs_panel(actor) -> None:
    """Edit catalog_test_specs rows (Admin only)."""
    render_section_title(
        "Test catalog — methods & limits",
        "Database source of truth for built-in Food, Water, and Micro tests. "
        "Each save creates a new version; the live row is always the latest. "
        "Custom formulas are managed separately.",
    )

    cat_keys = list(SAMPLE_CATEGORIES.keys())
    cat_labels = [SAMPLE_CATEGORIES[k] for k in cat_keys]
    selected_label = st.selectbox(
        "Filter by category",
        options=["All"] + cat_labels,
        key="catalog_specs_cat_filter",
    )
    filter_cat = None
    if selected_label != "All":
        filter_cat = cat_keys[cat_labels.index(selected_label)]

    specs = list_all_specs(filter_cat)
    if not specs:
        st.info("No catalog specs in the database. Run migrations or restart the app.")
        return

    options = [
        f"{s.test_key} — {s.test_name} ({SAMPLE_CATEGORIES.get(s.category, s.category)})"
        for s in specs
    ]
    choice = st.selectbox("Select test", options=options, key="catalog_specs_select")
    idx = options.index(choice)
    spec = specs[idx]

    st.caption(
        f"**Key:** `{spec.test_key}` · **Category:** {spec.category} · "
        f"**Version:** {spec.version_label}"
    )

    is_water = spec.category == "water"
    with st.form("catalog_spec_edit_form"):
        test_name = st.text_input("Test name", value=spec.test_name)
        method = st.text_input("Method of analysis", value=spec.method_of_analysis)
        if is_water:
            limits_desirable = st.text_input(
                "Desirable limit (IS 10500)",
                value=spec.limits_desirable or "",
            )
            limits_permissible = st.text_input(
                "Permissible limit (IS 10500)",
                value=spec.limits_permissible or "",
            )
            limits_text = spec.limits_text or ""
        else:
            limits_desirable = spec.limits_desirable or ""
            limits_permissible = spec.limits_permissible or ""
            limits_text = st.text_input(
                "Limits",
                value=spec.limits_text or "",
                help="Micro qualitative limits (e.g. Shall be Absent).",
            )
        default_unit = st.text_input("Default unit", value=spec.default_unit or "")
        unit_editable = st.checkbox(
            "Analyst can edit unit at intake",
            value=spec.unit_editable,
        )
        sort_order = st.number_input(
            "Sort order",
            min_value=0,
            max_value=999,
            value=int(spec.sort_order),
            step=1,
        )
        edit_reason = edit_reason_field(key="catalog_spec_edit_reason")
        submitted = st.form_submit_button("Save as new version", type="primary")

    if submitted:
        if not require_edit_reason(edit_reason):
            return
        try:
            updated = update_spec(
                spec.test_key,
                test_name=test_name,
                method_of_analysis=method,
                limits_text=limits_text if not is_water else None,
                limits_desirable=limits_desirable if is_water else None,
                limits_permissible=limits_permissible if is_water else None,
                default_unit=default_unit,
                unit_editable=unit_editable,
                sort_order=int(sort_order),
                edit_reason=edit_reason,
                actor=actor,
            )
            st.success(
                f"Saved **{updated.test_name}** as {updated.version_label}."
            )
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    versions = list_spec_versions(spec.test_key, limit=10)
    if versions:
        with st.expander("Version history", expanded=False):
            for v in versions:
                snap = v.snapshot()
                st.markdown(
                    f"**v{v.version_no}** — {v.user_name} — "
                    f"{v.created_at:%Y-%m-%d %H:%M} — {v.edit_reason}"
                )
                st.caption(_version_summary(snap))

    st.dataframe(
        [
            {
                "Key": s.test_key,
                "Category": s.category,
                "Name": s.test_name,
                "Version": s.version_label,
                "Method": s.method_of_analysis,
                "Limits": s.limits_display or "—",
                "Unit": s.default_unit or "—",
                "Unit editable": "Yes" if s.unit_editable else "No",
            }
            for s in specs
        ],
        use_container_width=True,
        hide_index=True,
    )
