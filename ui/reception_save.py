"""
ui/reception_save.py
--------------------
Shared save + CTR download helpers for Reception intake tabs.
"""

from __future__ import annotations

import streamlit as st

from services.audit import (
    document_actor_display_name,
    format_stamp_datetime,
    log_from_user,
    now_lab,
)
from services.customers import customer_data_changed, get_customer_by_gst, get_customer_by_id, gst_ready_for_lookup
from services.ctr_pdf import generate_ctr_documents
from services.docx_to_pdf import format_word_conversion_error
from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER, normalize_category
from services.requests import TestRequestData, save_test_request, validate_request, validation_warnings
from services.samples import REPORT_FORMAT_WITH_LOGO, report_format_label
from services.test_packages import describe_sample_package, get_package, package_status_label
from ui.components import require_edit_reason, render_section_title


def render_ctr_downloads(saved, actor, gen_by: str, gen_at: str) -> None:
    """Show success message, sample codes table, and PDF/DOCX download buttons."""
    docx_bytes = None
    pdf_bytes = None
    docx_name = ""
    pdf_name = ""
    docx_error = None
    pdf_error = None
    try:
        with st.spinner("Generating Customer Test Request (Word + PDF)…"):
            (
                docx_bytes,
                pdf_bytes,
                docx_name,
                pdf_name,
                pdf_error,
            ) = generate_ctr_documents(
                saved, generated_by=gen_by, generated_at=gen_at
            )

        log_from_user(
            actor,
            "report.ctr",
            "test_requests",
            saved.request_id,
            details=f"lab={saved.lab_code or ''}",
        )
    except Exception as exc:  # noqa: BLE001
        docx_error = str(exc)
        st.error(f"Generate failed: {docx_error}")
        return

    render_section_title("Saved — sample codes & downloads")
    st.success(
        f"Request saved (ID #{saved.request_id}). "
        f"Customer ID #{saved.customer.id}"
        + (
            f" (GST {saved.customer.gst_number})"
            if (saved.customer.gst_number or "").strip()
            else ""
        )
        + "."
    )
    st.caption(
        "Download filled PDF (standard form layout with lab header/footer) or Word (.docx) "
        "with full letterhead from the CTR template."
    )

    if saved.samples:
        render_section_title(
            "Sample codes for analyst",
            "Write these codes on sample labels. Analyst opens them in the Analyst page.",
        )
        code_rows = []
        for s in saved.samples:
            cat = normalize_category(getattr(s, "category", "food"))
            pkg_label = "—"
            pkg_version = "—"
            pkg_status = "—"
            if cat == CATEGORY_FOOD:
                ptype = getattr(s, "package_type", None)
                if s.package_id:
                    pkg = get_package(s.package_id)
                    if pkg:
                        pkg_label = pkg.display_label
                    pkg_version = (
                        str(s.package_version_no)
                        if s.package_version_no is not None
                        else "—"
                    )
                    desc = describe_sample_package(
                        s.sample_name or "",
                        ptype or "",
                        pinned_package_id=s.package_id,
                        pinned_version_no=s.package_version_no,
                    )
                    pkg_status = package_status_label(desc)
                elif ptype:
                    desc = describe_sample_package(
                        s.sample_name or "",
                        ptype,
                    )
                    pkg_status = package_status_label(desc)
                    if desc.get("display_label"):
                        pkg_label = desc["display_label"]
            code_rows.append(
                {
                    "Sample code": s.sample_code,
                    "Protocol No": getattr(s, "protocol_no", "") or "—",
                    "Sr.": s.sr_no,
                    "Name of sample": s.sample_name,
                    "Batch": s.batch_code,
                    "Qty": s.quantity,
                    "Package": pkg_label,
                    "Pkg version": pkg_version,
                    "Package status": pkg_status,
                    "Assigned analyst": getattr(s, "assigned_analyst_name", "") or "—",
                    "Micro analyst": (
                        getattr(s, "assigned_micro_analyst_name", "") or "—"
                        if normalize_category(getattr(s, "category", "food"))
                        == CATEGORY_WATER
                        else "—"
                    ),
                    "Report format": report_format_label(
                        getattr(s, "report_format", REPORT_FORMAT_WITH_LOGO)
                    ),
                    "Tests to perform": s.parameters,
                    "Status": getattr(s, "status", "pending"),
                }
            )
        st.dataframe(code_rows, use_container_width=True, hide_index=True)

    d1, d2 = st.columns(2)
    with d1:
        if pdf_bytes is not None:
            st.download_button(
                label="Download filled PDF",
                data=pdf_bytes,
                file_name=pdf_name,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        elif pdf_error:
            st.warning(f"PDF not available: {format_word_conversion_error(pdf_error)}")
        else:
            st.warning("PDF not available.")
    with d2:
        if docx_bytes is not None:
            st.download_button(
                label="Download filled Word (.docx)",
                data=docx_bytes,
                file_name=docx_name,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                use_container_width=True,
            )

    if pdf_bytes is not None:
        st.session_state["last_pdf_bytes"] = pdf_bytes
        st.session_state["last_pdf_name"] = pdf_name


def submit_new_intake_request(
    data: TestRequestData,
    actor,
    *,
    form_edit_reason: str = "",
) -> bool:
    """
    Validate and save a new CTR intake request; render downloads on success.

    Returns True when save completed.
    """
    errors = validate_request(data)
    if errors:
        st.error("Please fix the following before saving:")
        for e in errors:
            st.write(f"• {e}")
        return False

    for w in validation_warnings(data):
        st.warning(w)

    edit_reason = (form_edit_reason or "").strip()
    if not edit_reason:
        edit_reason = str(
            st.session_state.get("new_ctr_customer_edit_reason", "") or ""
        ).strip()

    existing = None
    if gst_ready_for_lookup(data.customer.gst_number):
        existing = get_customer_by_gst(data.customer.gst_number)
    elif data.customer.id is not None:
        existing = get_customer_by_id(data.customer.id)
    if existing and customer_data_changed(existing, data.customer):
        if not require_edit_reason(edit_reason):
            return False

    gen_by = document_actor_display_name(actor)
    gen_at = format_stamp_datetime(now_lab())

    try:
        with st.spinner("Saving customer, request & sample codes…"):
            saved = save_test_request(data, actor=actor, edit_reason=edit_reason or None)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Save failed: {exc}")
        st.info(
            "If you see a database schema error, apply pending migrations. "
            "From the project root:\n\n"
            '`python -c "from db.migrate import ensure_schema; ensure_schema(force=True)"`'
        )
        return False

    render_ctr_downloads(saved, actor, gen_by, gen_at)
    return True
