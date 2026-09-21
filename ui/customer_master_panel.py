"""
ui/customer_master_panel.py
-----------------------------
Standalone customer master CRUD for Reception (Tab 2).
"""

from __future__ import annotations

import streamlit as st

from services.customers import (
    customer_data_changed,
    get_customer_by_gst,
    get_customer_by_id,
    gst_ready_for_lookup,
    upsert_customer,
)
from ui.components import (
    apply_customer_to_session,
    customer_picker,
    edit_reason_field,
    read_customer_from_session,
    render_customer_details_form,
    render_section_title,
    require_edit_reason,
)


def _validate_customer_for_save(customer) -> list[str]:
    errors: list[str] = []
    if not (customer.customer_name or "").strip():
        errors.append("Customer name is required.")
    if not (customer.address or "").strip():
        errors.append("Address is required.")
    if not (customer.contact_number or "").strip():
        errors.append("Contact number is required.")
    contacts = customer.resolved_contacts()
    if not contacts or not (contacts[0].contact_name or "").strip():
        errors.append("Contact 1 name is required.")
    return errors


def render_customer_master_panel(actor) -> None:
    """Register or update permanent customers independent of sample intake."""
    render_section_title(
        "Customer master",
        "Save customer details and contact persons anytime. "
        "Use **New sample registration** to link a saved customer to a test request.",
    )

    picked = customer_picker(
        lookup_no=1,
        customer_details_no=2,
        key_prefix="cust_master_",
    )
    if picked is not None:
        apply_customer_to_session(picked)
        st.session_state["cust_master_customer_id"] = picked.id
    elif st.session_state.get("cust_master_customer_id"):
        existing = get_customer_by_id(int(st.session_state["cust_master_customer_id"]))
        if existing is not None:
            apply_customer_to_session(existing)

    st.divider()
    contact_count = render_customer_details_form(section_no=2, show_gst_autoload=True)

    existing_record = None
    draft = read_customer_from_session(contact_count=contact_count)
    if gst_ready_for_lookup(draft.gst_number):
        existing_record = get_customer_by_gst(draft.gst_number)
    elif draft.id is not None:
        existing_record = get_customer_by_id(draft.id)
    elif st.session_state.get("cust_master_customer_id"):
        existing_record = get_customer_by_id(int(st.session_state["cust_master_customer_id"]))

    needs_edit_reason = (
        existing_record is not None
        and customer_data_changed(existing_record, draft)
    )
    edit_reason = ""
    if needs_edit_reason:
        render_section_title(
            "Edit reason",
            "Required when updating an existing customer record.",
        )
        edit_reason = edit_reason_field(key="cust_master_edit_reason")

    if st.button("Save customer", type="primary", key="cust_master_save"):
        customer = read_customer_from_session(contact_count=contact_count)
        errors = _validate_customer_for_save(customer)
        if errors:
            for err in errors:
                st.error(err)
            return
        if needs_edit_reason and not require_edit_reason(edit_reason):
            return
        try:
            saved = upsert_customer(
                customer,
                edit_reason=edit_reason if needs_edit_reason else None,
                actor=actor,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
            return
        st.session_state["cust_master_customer_id"] = saved.id
        apply_customer_to_session(saved)
        gst = (saved.gst_number or "").strip()
        st.success(
            f"Saved customer **{saved.customer_name}** (ID #{saved.id}"
            + (f", GST {gst}" if gst else "")
            + ")."
        )
