"""
pages/1_Reception.py
--------------------
Reception workspace: Customer Test Request intake and edits.

Saves permanent customer + request, creates one DB row per sample with an
auto-derived sample_code and tests_to_perform, then offers PDF/DOCX download.
Edits to existing customers or requests require a written reason and create a version.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db.connection import test_connection  # noqa: E402
from services.audit import (  # noqa: E402
    actor_display_name,
    format_stamp_datetime,
    log_from_user,
    now_lab,
)
from services.auth import get_session_user  # noqa: E402
from services.customers import customer_data_changed, get_customer_by_gst  # noqa: E402
from services.docx_filler import fill_docx_bytes, suggest_docx_filename  # noqa: E402
from services.pdf_generator import generate_pdf_bytes, suggest_pdf_filename  # noqa: E402
from services.requests import (  # noqa: E402
    get_test_request,
    save_test_request,
    search_test_requests,
    update_test_request,
    validate_request,
    validation_warnings,
)
from services.samples import (  # noqa: E402
    REPORT_FORMAT_WITH_LOGO,
    delete_expired_samples,
    report_format_label,
)
from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category  # noqa: E402
from services.test_packages import (  # noqa: E402
    describe_sample_package,
    get_package,
    package_status_label,
)
from ui.auth import require_page_access  # noqa: E402
from ui.components import (  # noqa: E402
    apply_request_prefill,
    clear_ctr_form_state,
    collect_form,
    customer_picker,
    edit_reason_field,
    inject_styles,
    render_db_status,
    render_hero,
    render_section_title,
    require_edit_reason,
)

_MODE_NEW = "New request"
_MODE_EDIT = "Edit existing request"
_MODE_PACKAGES = "Test packages"
_RECEPTION_MODES = (_MODE_NEW, _MODE_EDIT, _MODE_PACKAGES)

st.set_page_config(
    page_title="S Testing Laboratory — Reception",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _render_downloads(saved, actor, gen_by: str, gen_at: str) -> None:
    try:
        with st.spinner("Generating filled PDF…"):
            pdf_bytes = generate_pdf_bytes(
                saved, generated_by=gen_by, generated_at=gen_at
            )

        docx_bytes = None
        docx_error = None
        try:
            docx_bytes = fill_docx_bytes(
                saved, generated_by=gen_by, generated_at=gen_at
            )
        except Exception as exc:  # noqa: BLE001
            docx_error = str(exc)

        log_from_user(
            actor,
            "report.ctr",
            "test_requests",
            saved.request_id,
            details=f"lab={saved.lab_code or ''}",
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Generate failed: {exc}")
        return

    render_section_title("Saved — sample codes & downloads")
    st.success(
        f"Request saved (ID #{saved.request_id}). "
        f"Customer ID #{saved.customer.id} (GST {saved.customer.gst_number})."
    )
    st.caption(
        "Download filled PDF or Word (.docx). Both match the Customer Test Request form."
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
        st.download_button(
            label="Download filled PDF",
            data=pdf_bytes,
            file_name=suggest_pdf_filename(saved),
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    with d2:
        if docx_bytes is not None:
            st.download_button(
                label="Download filled Word (.docx)",
                data=docx_bytes,
                file_name=suggest_docx_filename(saved),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                use_container_width=True,
            )
        else:
            st.warning(f"Word download unavailable: {docx_error}")

    st.session_state["last_pdf_bytes"] = pdf_bytes
    st.session_state["last_pdf_name"] = suggest_pdf_filename(saved)


def _new_request_flow(actor) -> None:
    selected_customer = customer_picker()
    st.divider()

    if selected_customer is not None:
        render_section_title(
            "Edit reason (customer updates)",
            "Required if you change permanent customer details for an existing GST record.",
        )
        edit_reason_field(key="new_ctr_customer_edit_reason")

    result = collect_form(selected_customer)
    if result is None:
        st.caption(
            "Tip: fill sample name (and Parameters for Food). Sample IDs preview "
            "live in Section 6 from the Lab Code. Code/batch no. is optional "
            "customer reference."
        )
        return

    data, _form_reason = result
    errors = validate_request(data)
    if errors:
        st.error("Please fix the following before saving:")
        for e in errors:
            st.write(f"• {e}")
        return

    for w in validation_warnings(data):
        st.warning(w)

    edit_reason = (_form_reason or "").strip()
    if not edit_reason:
        edit_reason = str(
            st.session_state.get("new_ctr_customer_edit_reason", "") or ""
        ).strip()

    existing = get_customer_by_gst(data.customer.gst_number)
    if existing and customer_data_changed(existing, data.customer):
        if not require_edit_reason(edit_reason):
            return

    gen_by = actor_display_name(actor)
    gen_at = format_stamp_datetime(now_lab())

    try:
        with st.spinner("Saving customer, request & sample codes…"):
            saved = save_test_request(data, actor=actor, edit_reason=edit_reason or None)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Save failed: {exc}")
        st.info(
            "If you see a column error, run migrations:\n\n"
            "`docker exec -i sls_lab_db psql -U sls_user -d sls_lab "
            "< scripts/migrate_versions.sql`"
        )
        return

    _render_downloads(saved, actor, gen_by, gen_at)


def _on_reception_mode_change() -> None:
    clear_ctr_form_state()


def _edit_request_option_label(result) -> str:
    return (
        f"#{result.request_id}  |  {result.lab_code or '—'}  |  {result.customer_name}  "
        f"({result.sample_count} samples: {result.sample_codes or '—'})"
    )


def _on_edit_request_select() -> None:
    results = st.session_state.get("edit_request_results", [])
    if not results:
        return
    choice = st.session_state.get("edit_request_select")
    options = [_edit_request_option_label(r) for r in results]
    try:
        idx = options.index(choice)
    except ValueError:
        return
    request_data = get_test_request(results[idx].request_id)
    if request_data is not None:
        apply_request_prefill(request_data)


def _edit_request_flow(actor) -> None:
    render_section_title(
        "Find existing request",
        "Search by lab code, sample code, or customer name.",
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        search_q = st.text_input(
            "Search",
            key="edit_request_search_q",
            placeholder="Lab code, sample code, or customer name",
        )
    with c2:
        st.write("")
        st.write("")
        do_search = st.button("Search requests", use_container_width=True)

    if do_search or "edit_request_results" not in st.session_state:
        try:
            st.session_state["edit_request_results"] = search_test_requests(search_q)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Search failed: {exc}")
            st.session_state["edit_request_results"] = []

    results = st.session_state.get("edit_request_results", [])
    if not results:
        st.info("No matching requests. Try another search term.")
        return

    options = [_edit_request_option_label(r) for r in results]
    choice = st.selectbox(
        "Select request to edit",
        options,
        key="edit_request_select",
        on_change=_on_edit_request_select,
    )
    idx = options.index(choice)
    request_id = results[idx].request_id

    request_data = get_test_request(request_id)
    if request_data is None:
        st.error("Could not load the selected request.")
        return

    non_pending = [s for s in request_data.samples if s.status != "pending"]
    if non_pending:
        st.warning(
            "Some samples have analyst activity — sample codes cannot be changed "
            "and those rows cannot be removed. Locked: "
            + ", ".join(f"{s.sample_code} ({s.status})" for s in non_pending)
        )

    st.divider()
    result = collect_form(
        request_data.customer,
        request_prefill=request_data,
        edit_mode=True,
        submit_label="Save changes & regenerate form",
    )
    if result is None:
        return

    data, edit_reason = result
    if not require_edit_reason(edit_reason):
        return

    errors = validate_request(data)
    if errors:
        st.error("Please fix the following before saving:")
        for e in errors:
            st.write(f"• {e}")
        return

    for w in validation_warnings(data):
        st.warning(w)

    gen_by = actor_display_name(actor)
    gen_at = format_stamp_datetime(now_lab())

    try:
        with st.spinner("Saving version & updated request…"):
            saved = update_test_request(data, edit_reason, actor=actor)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Update failed: {exc}")
        return

    _render_downloads(saved, actor, gen_by, gen_at)


def main() -> None:
    require_page_access("reception")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Reception — Customer Test Request",
        subtitle=(
            "Capture customer & sample intake, or edit an existing request. "
            "Changes to existing data require a written reason and are versioned."
        ),
        badge="Reception desk",
    )

    ok, msg = test_connection()
    render_db_status(ok, msg)
    st.write("")
    if not ok:
        st.error("Database not connected. Start Docker Postgres, then refresh.")
        st.stop()

    if not st.session_state.get("_reception_purged"):
        try:
            delete_expired_samples(actor=actor)
        except Exception:  # noqa: BLE001
            pass
        st.session_state["_reception_purged"] = True

    mode = st.radio(
        "Workspace",
        options=_RECEPTION_MODES,
        horizontal=True,
        key="reception_mode",
        on_change=_on_reception_mode_change,
        label_visibility="collapsed",
    )
    st.write("")

    if mode == _MODE_NEW:
        _new_request_flow(actor)
    elif mode == _MODE_EDIT:
        _edit_request_flow(actor)
    else:
        from ui.test_packages_panel import render_test_packages_panel

        render_test_packages_panel(actor)


main()
