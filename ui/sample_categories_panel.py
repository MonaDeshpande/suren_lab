"""
ui/sample_categories_panel.py
-----------------------------
Admin UI to add extra sample categories (e.g. Pharma) for custom formulas.
"""

from __future__ import annotations

import streamlit as st

from services.sample_categories import (
    create_category,
    list_categories,
    set_category_active,
)
from ui.components import render_section_title


def render_sample_categories_panel(actor) -> None:
    """Add or deactivate admin-defined sample categories."""
    render_section_title(
        "Sample categories",
        "Built-in categories (Food, Water, Micro, Cattle Feed / Fertilizer) stay "
        "locked. Add extras such as **Pharma** so Reception and custom formulas "
        "can use them.",
    )

    rows = list_categories(active_only=False)
    if rows:
        st.dataframe(
            [
                {
                    "Key": c.category_key,
                    "Label": c.label,
                    "Built-in": "Yes" if c.is_builtin else "No",
                    "Active": "Yes" if c.is_active else "No",
                }
                for c in rows
            ],
            use_container_width=True,
            hide_index=True,
        )

    with st.form("sample_category_create_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_key = st.text_input(
                "Category key *",
                placeholder="pharma",
                help="Lowercase letters, digits, underscores (e.g. pharma).",
            )
        with c2:
            new_label = st.text_input("Display label *", placeholder="Pharma")
        submitted = st.form_submit_button("Add category", type="primary")

    if submitted:
        try:
            created = create_category(new_key, new_label, actor=actor)
            st.success(f"Added category **{created.label}** (`{created.category_key}`).")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not add category: {exc}")

    extras = [c for c in rows if not c.is_builtin]
    if not extras:
        st.caption("No extra categories yet. Add **pharma** to use custom formulas there.")
        return

    st.markdown("**Deactivate / reactivate extra categories**")
    for cat in extras:
        cols = st.columns([3, 1])
        with cols[0]:
            status = "active" if cat.is_active else "inactive"
            st.markdown(f"`{cat.category_key}` — {cat.label} ({status})")
        with cols[1]:
            btn_label = "Deactivate" if cat.is_active else "Activate"
            if st.button(btn_label, key=f"sc_toggle_{cat.category_key}"):
                try:
                    set_category_active(
                        cat.category_key,
                        is_active=not cat.is_active,
                        actor=actor,
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
