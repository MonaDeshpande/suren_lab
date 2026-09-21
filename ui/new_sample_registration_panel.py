"""
ui/new_sample_registration_panel.py
-----------------------------------
New sample / CTR intake: pick saved customer + package, then complete request.
"""

from __future__ import annotations

import streamlit as st

from services.customers import get_customer_by_id
from services.test_packages import search_packages
from ui.components import (
    apply_pinned_package_to_intake,
    collect_form,
    customer_picker,
    render_section_title,
)
from ui.reception_save import submit_new_intake_request


def _package_picker_label(pkg) -> str:
    return (
        f"{pkg.sample_product_name} — {pkg.package_type_label} "
        f"(v{pkg.current_version_no}, WL:{len(pkg.test_keys_with_logo)} / "
        f"NWL:{len(pkg.test_keys_without_logo)})"
    )


def render_new_sample_registration_panel(actor) -> None:
    """Tab 3 — new CTR intake using saved customer and package."""
    render_section_title(
        "New sample registration",
        "Select a **saved customer** and **test package**, then complete "
        "request details, samples, and lab workflow.",
    )

    picked = customer_picker(
        lookup_no=1,
        customer_details_no=2,
        key_prefix="intake_",
    )
    if picked is not None and picked.id is not None:
        st.session_state["intake_customer_id"] = picked.id
    elif st.session_state.get("intake_customer_id"):
        refreshed = get_customer_by_id(int(st.session_state["intake_customer_id"]))
        if refreshed is not None:
            picked = refreshed

    cust_id = st.session_state.get("intake_customer_id")
    if not cust_id:
        st.info(
            "Select a customer above, or register one under the **Customers** tab."
        )
        return

    customer = get_customer_by_id(int(cust_id))
    if customer is None:
        st.error("Selected customer was not found. Pick another customer.")
        st.session_state.pop("intake_customer_id", None)
        return

    primary = customer.resolved_contacts()
    contact_name = primary[0].contact_name if primary else customer.contact_person
    st.markdown(
        f"**Customer:** {customer.customer_name or '—'}  \n"
        f"**GST:** {customer.gst_number or '—'}  \n"
        f"**Contact:** {contact_name or '—'} · {customer.contact_number or '—'}"
    )
    st.caption(
        "To change customer details, use the **Customers** tab, then return here."
    )

    st.divider()
    render_section_title(
        "Test package (product)",
        "Search and select a registered package — the first sample row is pre-filled.",
    )
    pkg_query = st.text_input(
        "Search package / product name",
        key="intake_package_search_q",
        placeholder="e.g. Jaggery, Paneer, Masala",
    )
    packages = search_packages(pkg_query, active_only=True, limit=40)
    pinned_id = st.session_state.get("intake_pinned_package_id")
    if not packages:
        st.warning(
            "No matching packages. Define products under **Sample registration** first."
        )
    else:
        labels = [_package_picker_label(p) for p in packages]
        default_idx = 0
        if pinned_id:
            for i, pkg in enumerate(packages):
                if pkg.id == int(pinned_id):
                    default_idx = i
                    break
        choice = st.selectbox(
            "Select package",
            options=labels,
            index=default_idx,
            key="intake_package_select",
        )
        idx = labels.index(choice)
        selected_pkg = packages[idx]
        if st.button("Apply package to sample table", key="intake_apply_package"):
            apply_pinned_package_to_intake(selected_pkg)
            st.success(f"Applied package **{selected_pkg.sample_product_name}**.")
            st.rerun()

    st.divider()
    pinned = st.session_state.get("intake_pinned_package_id")
    result = collect_form(
        prefill=customer,
        sample_first=True,
        customer_from_master=True,
        pinned_package_id=int(pinned) if pinned else None,
        actor=actor,
    )
    if result is None:
        return

    data, form_reason = result
    submit_new_intake_request(data, actor, form_edit_reason=form_reason or "")
