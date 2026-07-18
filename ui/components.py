"""
ui/components.py
----------------
Reusable Streamlit UI building blocks for the Customer Test Request form.

Keeping widgets here keeps app.py focused on page flow / orchestration.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from services.branding import LOGO_PATH
from services.customers import Customer, get_customer_by_id, search_customers
from services.requests import SampleRow, TestRequestData


# Path to the CSS file next to this module
STYLES_PATH = Path(__file__).resolve().parent / "styles.css"


def inject_styles() -> None:
    """Load custom CSS into the Streamlit page."""
    if STYLES_PATH.exists():
        css = STYLES_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_hero(
    title: str = "S Testing Laboratory",
    subtitle: str = (
        "Customer Test Request — capture intake details, save permanent "
        "customer records, and generate a filled request form."
    ),
    badge: str = "Quality &amp; Food Safety Testing",
) -> None:
    """Top brand banner for the food testing lab (letterhead + title)."""
    logo_html = ""
    if LOGO_PATH.exists():
        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo_html = (
            '<div class="sls-letterhead">'
            f'<img src="data:image/png;base64,{b64}" alt="Letterhead logo" />'
            "</div>"
        )

    st.markdown(
        f"""
        <div class="sls-hero">
          {logo_html}
          <h1>{title}</h1>
          <p>{subtitle}</p>
          <div class="sls-badge">{badge}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_title(title: str, hint: str = "") -> None:
    """Consistent section heading + optional helper text."""
    st.markdown(f'<div class="sls-section-title">{title}</div>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<div class="sls-hint">{hint}</div>', unsafe_allow_html=True)


def render_db_status(ok: bool, message: str) -> None:
    """Show database connectivity status near the top of the page."""
    cls = "sls-status-ok" if ok else "sls-status-err"
    label = "Database connected" if ok else "Database connection failed"
    st.markdown(
        f'<div class="{cls}"><b>{label}</b> — {message}</div>',
        unsafe_allow_html=True,
    )


def customer_picker() -> Optional[Customer]:
    """
    Search / select an existing permanent customer.

    Returns
    -------
    Customer or None
        Selected customer to autofill the form, or None if user chose "New".
    """
    render_section_title(
        "1. Existing customer lookup",
        "Permanent fields (name, address, contact, email, GST) are stored in "
        "PostgreSQL and reused. Search by GST or customer name, or start a new record.",
    )

    col_q, col_btn = st.columns([3, 1])
    with col_q:
        query = st.text_input(
            "Search GST / customer name",
            placeholder="e.g. 27AAAAA0000A1Z5 or Acme Foods",
            key="customer_search_q",
        )
    with col_btn:
        st.write("")  # vertical align
        st.write("")
        do_search = st.button("Search", use_container_width=True)

    # Cache last search results in session_state
    if do_search or "customer_search_results" not in st.session_state:
        try:
            st.session_state["customer_search_results"] = search_customers(query)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not search customers: {exc}")
            st.session_state["customer_search_results"] = []

    results: list[Customer] = st.session_state.get("customer_search_results", [])

    options = ["— New customer —"] + [
        f"{c.customer_name}  |  GST: {c.gst_number}  (#{c.id})" for c in results
    ]
    choice = st.selectbox("Select customer to autofill", options, key="customer_select")

    if choice == "— New customer —" or not results:
        return None

    # Map label back to Customer object
    idx = options.index(choice) - 1
    selected = results[idx]
    # Re-fetch by id to ensure we have the latest DB row
    if selected.id is not None:
        fresh = get_customer_by_id(selected.id)
        return fresh or selected
    return selected


def _sync_customer_prefill(prefill: Optional[Customer]) -> Customer:
    """
    Keep permanent customer fields in session_state so selecting a customer
    from the picker actually updates the form widgets.

    Streamlit only honours widget `value=` on first creation; after that we
    must write into st.session_state[key] when the selected customer changes.
    """
    empty = Customer(
        customer_name="",
        address="",
        contact_person="",
        contact_number="",
        email="",
        gst_number="",
    )
    p = prefill or empty
    selected_key = p.id if p.id is not None else "new"

    # When the picker selection changes, push values into widget session keys
    if st.session_state.get("_prefill_customer_key") != selected_key:
        st.session_state["_prefill_customer_key"] = selected_key
        st.session_state["f_customer_name"] = p.customer_name
        st.session_state["f_address"] = p.address
        st.session_state["f_contact_person"] = p.contact_person
        st.session_state["f_contact_number"] = p.contact_number
        st.session_state["f_email"] = p.email
        st.session_state["f_gst_number"] = p.gst_number

    # Ensure keys exist even on first run with no picker change
    for key, default in [
        ("f_customer_name", p.customer_name),
        ("f_address", p.address),
        ("f_contact_person", p.contact_person),
        ("f_contact_number", p.contact_number),
        ("f_email", p.email),
        ("f_gst_number", p.gst_number),
    ]:
        st.session_state.setdefault(key, default)

    return p


def collect_form(prefill: Optional[Customer]) -> Optional[TestRequestData]:
    """
    Render the main intake form and return a TestRequestData on submit.

    Parameters
    ----------
    prefill : existing customer to autofill permanent fields (or None)

    Returns
    -------
    TestRequestData if the user clicked Submit, else None.
    """
    from services.protocols.test_catalog import (
        SAMPLE_CATEGORIES,
        TEST_CATALOG,
        filter_keys_for_category,
        list_tests_for_select,
        normalize_category,
    )

    p = _sync_customer_prefill(prefill)

    # Category + tests sit outside the form so the multiselect can refilter live.
    render_section_title(
        "2. Sample category & catalog tests",
        "Choose Food, Water, or Cattle Feed / Fertilizer — only matching tests "
        "appear. Set the same category on each sample row in the table below.",
    )
    cat_keys = list(SAMPLE_CATEGORIES.keys())
    cat_labels = [SAMPLE_CATEGORIES[k] for k in cat_keys]
    selected_cat_label = st.selectbox(
        "Sample category *",
        options=cat_labels,
        index=0,
        key="sample_category_select",
        help="Filters the test list. Each sample row should use this category "
        "(or change the Category column per row for mixed requests).",
    )
    filter_category = cat_keys[cat_labels.index(selected_cat_label)]

    catalog_options = list_tests_for_select(filter_category)
    if not catalog_options:
        st.info(
            f"No catalog tests are defined yet for **{selected_cat_label}**. "
            "Food currently has 11 tests; Water and Cattle Feed / Fertilizer "
            "formulas will appear here when added."
        )
        selected_keys: list[str] = []
    else:
        selected_labels = st.multiselect(
            f"Catalog tests to perform ({selected_cat_label})",
            options=[lbl for _, lbl in catalog_options],
            help="Only tests for the selected category are listed.",
            key=f"catalog_tests_multiselect_{filter_category}",
        )
        label_to_key = {lbl: k for k, lbl in catalog_options}
        selected_keys = [
            label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key
        ]

    with st.form("ctr_form", clear_on_submit=False):
        # ----- Permanent customer block -----
        render_section_title(
            "3. Customer details (permanent database)",
            "These fields are upserted into PostgreSQL using GST number as the unique key.",
        )

        c1, c2 = st.columns(2)
        with c1:
            customer_name = st.text_input(
                "Customer Details (Name / Company) *",
                key="f_customer_name",
            )
            contact_person = st.text_input(
                "Name of Contact Person *",
                key="f_contact_person",
            )
            email = st.text_input("Email ID *", key="f_email")
        with c2:
            address = st.text_area("Address *", height=100, key="f_address")
            contact_number = st.text_input(
                "Contact Number *",
                key="f_contact_number",
            )
            gst_number = st.text_input(
                "GST Number *",
                key="f_gst_number",
                help="Used as the permanent unique key for this customer.",
            )

        # ----- Request-specific block -----
        render_section_title("4. Test request details")

        r1, r2, r3 = st.columns(3)
        with r1:
            request_date = st.date_input("Date *", value=date.today())
        with r2:
            lab_code = st.text_input("Lab Code", placeholder="e.g. LAB/CTR/26/001")
        with r3:
            number_of_samples = st.number_input(
                "Number of Samples",
                min_value=0,
                max_value=100,
                value=1,
                step=1,
            )

        r4, r5 = st.columns(2)
        with r4:
            sampling_choice = st.radio(
                "Sampling Done by Laboratory",
                options=["Not specified", "Yes", "No"],
                horizontal=True,
            )
            decision_choice = st.radio(
                "Decision Rule required",
                options=["Not specified", "Yes", "No"],
                horizontal=True,
            )
        with r5:
            service_type = st.radio(
                "Service required",
                options=["", "Urgent", "Regular"],
                format_func=lambda x: "Not specified" if x == "" else x,
                horizontal=True,
            )
            delivery_mode = st.selectbox(
                "Mode of report delivery",
                options=["", "Collect", "Courier", "Email/Whatsapp"],
                format_func=lambda x: "Not specified" if x == "" else x,
            )

        storage_temperature = st.text_input(
            "Storage Temperature of sample required",
            placeholder="e.g. Ambient / 2–8 °C / Frozen",
        )
        test_method_spec = st.text_area(
            "Specific test method / Specification to be followed",
            placeholder="e.g. FSSAI / IS method references",
            height=70,
        )
        payment_details = st.text_area(
            "Payment Details",
            placeholder="Advance amount, UTR, billing notes…",
            height=70,
        )
        sample_description = st.text_area(
            "Sample Description & tests to be performed (notes)",
            height=70,
        )

        # ----- Sample grid -----
        render_section_title(
            "5. Sample table",
            f"One row per sample. Category defaults to {selected_cat_label}; "
            "selected catalog tests are assigned to rows with a matching category.",
        )

        default_rows = [
            {
                "Sr. No": i,
                "Category": selected_cat_label,
                "Name of sample": "",
                "Code/batch no.": "",
                "Sample qty.": "",
            }
            for i in range(1, 6)
        ]
        sample_df = st.data_editor(
            pd.DataFrame(default_rows),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sr. No": st.column_config.NumberColumn("Sr. No", min_value=1, step=1),
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=cat_labels,
                    required=True,
                ),
                "Name of sample": st.column_config.TextColumn("Name of sample"),
                "Code/batch no.": st.column_config.TextColumn("Code/batch no."),
                "Sample qty.": st.column_config.TextColumn("Sample qty."),
            },
            key="sample_editor",
        )

        submitted = st.form_submit_button(
            "Save & Generate Form",
            use_container_width=True,
            type="primary",
        )

    if not submitted:
        return None

    # Map Yes/No radios to Optional[bool]
    def yn(choice: str) -> Optional[bool]:
        if choice == "Yes":
            return True
        if choice == "No":
            return False
        return None

    label_to_category = {v: k for k, v in SAMPLE_CATEGORIES.items()}
    samples: list[SampleRow] = []

    for i, row in enumerate(sample_df.to_dict(orient="records"), start=1):
        sr = row.get("Sr. No") or i
        try:
            sr_no = int(sr)
        except (TypeError, ValueError):
            sr_no = i
        row_category = normalize_category(
            label_to_category.get(str(row.get("Category") or "").strip(), filter_category)
        )
        row_keys = filter_keys_for_category(list(selected_keys), row_category)
        display_names = ", ".join(
            TEST_CATALOG[k].name for k in row_keys if k in TEST_CATALOG
        )
        samples.append(
            SampleRow(
                sr_no=sr_no,
                sample_name=str(row.get("Name of sample") or ""),
                batch_code=str(row.get("Code/batch no.") or ""),
                quantity=str(row.get("Sample qty.") or ""),
                parameters=display_names,
                test_keys=list(row_keys),
                category=row_category,
            )
        )

    customer = Customer(
        id=p.id,  # may be None for brand-new; upsert still keys on GST
        customer_name=customer_name,
        address=address,
        contact_person=contact_person,
        contact_number=contact_number,
        email=email,
        gst_number=gst_number,
    )

    return TestRequestData(
        customer=customer,
        request_date=request_date,
        lab_code=lab_code,
        number_of_samples=int(number_of_samples) if number_of_samples else None,
        sampling_by_lab=yn(sampling_choice),
        storage_temperature=storage_temperature,
        test_method_spec=test_method_spec,
        decision_rule=yn(decision_choice),
        service_type=service_type,
        delivery_mode=delivery_mode,
        payment_details=payment_details,
        sample_description=sample_description,
        samples=samples,
    )
