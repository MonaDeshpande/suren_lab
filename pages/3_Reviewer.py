"""
pages/3_Reviewer.py
-------------------
Reviewer workspace:

1. Find sample (lab code / sample / client) within 50-day window
2. Review Reception intake data
3. Review Analyst protocol header + test results
4. Preview final report fields → Generate Final Report PDF
5. Mark sample status as reported
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db.connection import test_connection  # noqa: E402
from services.branding import ORGANIZATION_NAME  # noqa: E402
from services.audit import (  # noqa: E402
    actor_display_name,
    format_stamp_datetime,
    log_from_user,
    now_lab,
)
from services.auth import get_session_user  # noqa: E402
from services.protocol_store import (  # noqa: E402
    format_analysis_date_range,
    get_protocol_header,
    list_results,
)
from services.protocols.test_catalog import (  # noqa: E402
    CATEGORY_MICRO,
    CATEGORY_WATER,
    normalize_category,
)
from services.samples import (  # noqa: E402
    SAMPLE_RETENTION_DAYS,
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITH_LOGO,
    SampleRecord,
    SEARCH_BY,
    default_report_with_logo,
    default_test_report_no,
    get_by_code,
    list_open,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
    report_format_label,
    search_open,
    update_status,
)
from services.report_settings import (  # noqa: E402
    default_authorized_signatory,
    load_report_settings,
    signatory_names,
)
from services.reviewer_report import (  # noqa: E402
    build_generation_params,
    generate_reviewer_final_report,
)
from services.test_report_pdf import (  # noqa: E402
    build_test_report_data,
    default_checked_by_analysts,
    suggest_test_report_filename,
)
from services.test_report_water_docx import (  # noqa: E402
    DEFAULT_TESTING_CONDUCTED_AT,
    WaterReportFillOptions,
    build_water_report_limit_rows,
)
from services.micro_report_catalog import (  # noqa: E402
    micro_report_keys_ordered,
    spec_for_key,
)
from services.reviewer_report_defaults import (  # noqa: E402
    default_reviewer_report_fields,
)
from services.ulr import (  # noqa: E402
    ULR_TOTAL_LENGTH,
    generate_ulr_no,
    lab_code_for_ulr,
)
from ui.auth import require_page_access  # noqa: E402
from ui.reviewer_state import (  # noqa: E402
    get_specs_df,
    get_widget,
    is_initialized,
    mark_initialized,
    on_sample_selected,
    set_specs_df,
    set_widget,
    set_widget_default,
    spec_editor_key,
    widget_key,
)
from ui.components import (  # noqa: E402
    inject_styles,
    render_db_status,
    render_hero,
    render_section_title,
)

st.set_page_config(
    page_title=f"{ORGANIZATION_NAME} — Reviewer",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)

_SEARCH_LABELS = {
    "lab_code": "Lab code",
    "sample": "Sample",
    "client": "Client name",
}

_SEARCH_PLACEHOLDERS = {
    "lab_code": "e.g. LAB/CTR/26/001",
    "sample": "Sample code or sample name",
    "client": "Customer / company name",
}


def _fmt_dt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def _samples_table_rows(samples: list[SampleRecord]) -> list[dict]:
    from services.protocols.test_catalog import category_label

    return [
        {
            "Lab code": s.lab_code or "—",
            "Sample code": s.sample_code,
            "Client": s.customer_name or "—",
            "Sample name": s.sample_name or "—",
            "Category": category_label(s.category),
            "Status": s.status,
            "Expires": _fmt_dt(s.expires_at),
        }
        for s in samples
    ]


def main() -> None:
    require_page_access("reviewer")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Reviewer — Final report",
        subtitle=(
            "Review <b>Reception</b> intake and <b>Analyst</b> results together, "
            "then generate the customer <b>Final Test Report</b> PDF (QSF 7.8.2)."
        ),
        badge="Review &amp; report",
    )

    ok, msg = test_connection()
    render_db_status(ok, msg)
    st.write("")
    if not ok:
        st.error("Database not connected.")
        st.stop()

    render_section_title(
        "1. Find sample",
        "Prefer status completed (analyst finished). In-progress samples show a warning.",
    )
    search_by = st.radio(
        "Search by",
        options=list(SEARCH_BY),
        format_func=lambda k: _SEARCH_LABELS[k],
        horizontal=True,
        key="reviewer_search_by",
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        search_query = st.text_input(
            _SEARCH_LABELS[search_by],
            placeholder=_SEARCH_PLACEHOLDERS[search_by],
            key="reviewer_search_query",
        )
    with c2:
        st.write("")
        st.write("")
        do_search = st.button("Search", type="primary", use_container_width=True)

    selected: Optional[SampleRecord] = None
    search_hits: list[SampleRecord] = []

    if do_search:
        if not search_query.strip():
            st.warning("Enter a search term.")
        else:
            search_hits = search_open(search_query, by=search_by)
            st.session_state["reviewer_search_hits"] = [
                s.sample_code for s in search_hits
            ]
            if not search_hits:
                st.info(f"No matching samples in the {SAMPLE_RETENTION_DAYS}-day window.")

    if "reviewer_search_hits" in st.session_state and not search_hits:
        codes = st.session_state.get("reviewer_search_hits") or []
        search_hits = [s for c in codes if (s := get_by_code(c))]

    if search_hits:
        st.dataframe(
            _samples_table_rows(search_hits),
            use_container_width=True,
            hide_index=True,
        )
        codes = [s.sample_code for s in search_hits]
        pick = st.selectbox(
            "Open sample",
            codes,
            key="reviewer_pick_code",
        )
        selected = get_by_code(pick) if pick else None
    else:
        st.caption("Or pick from the queue below.")
        queue = list_open(limit=50)
        if queue:
            st.dataframe(
                _samples_table_rows(queue),
                use_container_width=True,
                hide_index=True,
            )
            codes = [s.sample_code for s in queue]
            pick = st.selectbox(
                "Open from queue",
                ["—"] + codes,
                key="reviewer_queue_pick",
            )
            if pick and pick != "—":
                selected = get_by_code(pick)

    if selected is None:
        st.info("Select a sample to review.")
        return

    # Drop cached PDF when switching samples
    if st.session_state.get("reviewer_pdf_for") != selected.sample_code:
        st.session_state.pop("reviewer_pdf_bytes", None)
        st.session_state.pop("reviewer_pdf_name", None)
        st.session_state["reviewer_pdf_for"] = selected.sample_code

    on_sample_selected(selected.sample_code)
    code = selected.sample_code

    if selected.status == "in_progress":
        st.warning(
            "This sample is still **in progress**. Analyst may not have finished "
            "all tests."
        )
    elif selected.status == "pending":
        st.warning("This sample is still **pending** — analysis may not have started.")
    elif selected.status == "reported":
        st.info("Final report already generated for this sample (status: reported).")

    # ----- A. Reception -----
    st.divider()
    render_section_title("A. Reception data")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.markdown(f"**Client:** {selected.customer_name or '—'}")
        st.markdown(f"**Contact:** {selected.contact_person or '—'}")
        st.markdown(f"**Phone:** {selected.contact_number or '—'}")
    with r2:
        st.markdown(f"**Lab code:** {selected.lab_code or '—'}")
        st.markdown(f"**Sample code:** {selected.sample_code}")
        st.markdown(f"**Sample name:** {selected.sample_name or '—'}")
    with r3:
        st.markdown(f"**Batch:** {selected.batch_code or '—'}")
        st.markdown(f"**Quantity:** {selected.quantity or '—'}")
        st.markdown(f"**Status:** {selected.status}")

    st.markdown(f"**Address:** {selected.customer_address or '—'}")
    st.markdown(f"**GST:** {selected.customer_gst or '—'}")
    st.markdown(f"**Email:** {selected.customer_email or '—'}")
    st.markdown(f"**Tests requested:** {selected.tests_to_perform or '—'}")
    fmt = normalize_report_format(selected.report_format)
    st.markdown(f"**Report format:** {report_format_label(fmt)}")
    if fmt == REPORT_FORMAT_BOTH:
        from services.protocols.test_catalog import TEST_CATALOG

        with_logo = sorted(logo_test_keys(selected))
        without_logo = sorted(no_logo_test_keys(selected))
        with_labels = [TEST_CATALOG[k].name for k in with_logo if k in TEST_CATALOG]
        without_labels = [
            TEST_CATALOG[k].name for k in without_logo if k in TEST_CATALOG
        ]
        st.markdown(
            f"**Tests with logo:** {', '.join(with_labels) or '—'}"
        )
        st.markdown(
            f"**Tests without logo:** {', '.join(without_labels) or '—'}"
        )
    if selected.analyst_remarks:
        st.markdown(f"**Analyst remarks:** {selected.analyst_remarks}")

    # ----- B. Analyst -----
    st.divider()
    render_section_title("B. Analyst protocol & results")
    header = get_protocol_header(selected.id)
    results = list_results(selected.id)

    if header is None:
        st.warning("No protocol header saved yet.")
    else:
        h1, h2, h3 = st.columns(3)
        with h1:
            st.markdown(f"**Protocol no:** {header.protocol_no or '—'}")
            st.markdown(f"**Issued to:** {header.issued_to or '—'}")
        with h2:
            st.markdown(f"**Issued by:** {header.issued_by or '—'}")
            st.markdown(
                f"**Received on:** "
                f"{header.sample_received_on.isoformat() if header.sample_received_on else '—'}"
            )
        with h3:
            st.markdown(
                f"**Analysis date:** "
                f"{format_analysis_date_range(header.date_of_analysis_from, header.date_of_analysis_to, legacy_single=header.date_of_analysis) or '—'}"
            )
            st.markdown(f"**Appearance:** {header.appearance_text or '—'}")

    if not results:
        st.warning("No test results saved yet.")
    else:
        rows = [
            {
                "Test": r.test_name,
                "Method": r.method or "—",
                "Result": r.result_value or "—",
                "Unit": r.unit or "—",
            }
            for r in results
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ----- C. Final report -----
    st.divider()
    render_section_title(
        "C. Final report",
        "Preview fields, then generate the customer PDF.",
    )

    can_generate = header is not None and len(results) > 0
    if not can_generate:
        st.error(
            "Cannot generate final report until protocol header and at least one "
            "test result are saved."
        )
        return

    is_water = normalize_category(selected.category) == CATEGORY_WATER
    is_micro = normalize_category(selected.category) == CATEGORY_MICRO
    cond_key = widget_key("condition", code)
    tests_key = widget_key("tests_processed", code)
    appearance_key = widget_key("appearance", code)
    testing_at_key = widget_key("testing_at", code)
    ulr_key = widget_key("ulr", code)
    report_chem_key = widget_key("report_chem", code)
    report_micro_key = widget_key("report_micro", code)
    report_no_key = widget_key("report_no", code)
    customer_sid_key = widget_key("customer_sid", code)
    customer_addr_key = widget_key("customer_addr", code)
    report_date_key = widget_key("report_date", code)
    batch_no_key = widget_key("batch_no", code)
    lab_code_key = widget_key("lab_code", code)
    loc_key = widget_key("location", code)
    samp_method_key = widget_key("sampling_method", code)
    auth_key = widget_key("auth_signatory", code)
    remark_key = widget_key("remark", code)
    disclaimer_key = widget_key("disclaimer", code)
    report_settings = load_report_settings()
    signatory_options = signatory_names(report_settings) or [""]

    if is_water:
        if not is_initialized(code):
            set_widget_default("condition", code, "")
            set_widget_default("appearance", code, (header.appearance_text or "").strip())
            set_widget_default("testing_at", code, DEFAULT_TESTING_CONDUCTED_AT)
            set_widget_default(
                "ulr",
                code,
                generate_ulr_no(lab_code_for_ulr(selected.lab_code, selected.sample_code)),
            )
            report_no = default_test_report_no(
                selected, with_logo=default_report_with_logo(selected)
            )
            set_widget_default("report_chem", code, report_no)
            set_widget_default("report_micro", code, report_no)
            set_widget_default(
                "customer_sid",
                code,
                (selected.parameters or "").strip() or "Drinking Water",
            )
            set_widget_default("auth_signatory", code, default_authorized_signatory(report_settings))
            set_widget_default("checked_by", code, default_checked_by_analysts(selected))
            set_specs_df(code, pd.DataFrame(build_water_report_limit_rows(selected, results)))
            mark_initialized(code)

        p1, p2 = st.columns(2)
        with p1:
            st.markdown(
                f"**Name / address:**\n\n"
                f"{selected.customer_name or '—'}"
                f"{chr(10) + selected.customer_address if selected.customer_address else ''}"
            )
            st.markdown(f"**Sample:** {selected.sample_name or '—'}")
            st.markdown(f"**Lab code:** {selected.lab_code or selected.sample_code or '—'}")
        with p2:
            st.markdown(
                f"**Receipt date:** "
                f"{header.sample_received_on.strftime('%d/%m/%Y') if header.sample_received_on else '—'}"
            )
            st.markdown(
                f"**Analysis date:** "
                f"{format_analysis_date_range(header.date_of_analysis_from, header.date_of_analysis_to, legacy_single=header.date_of_analysis) or '—'}"
            )
            st.markdown(f"**Quantity:** {selected.quantity or '—'}")

        w1, w2 = st.columns(2)
        with w1:
            st.text_input("Condition of Sample", key=cond_key)
            st.text_input("Sample Appearance", key=appearance_key)
            st.text_input("Customer Sample ID", key=customer_sid_key)
            st.text_input("ULR No", key=ulr_key)
        with w2:
            st.text_input("Testing conducted at", key=testing_at_key)
            st.text_input("Report No (Chemical page)", key=report_chem_key)
            st.text_input("Report No (Physical/Micro page)", key=report_micro_key)

        specs_df = get_specs_df(code)
        if not specs_df.empty:
            st.markdown("**Test results and IS 10500 limits**")
            edited_specs = st.data_editor(
                specs_df,
                column_config={
                    "Test": st.column_config.TextColumn("Test key", disabled=True),
                    "Result": st.column_config.TextColumn("Result", disabled=True),
                    "Desirable Limit": st.column_config.TextColumn("Desirable Limit"),
                    "Permissible limit": st.column_config.TextColumn("Permissible limit"),
                    "Method": st.column_config.TextColumn("Method", disabled=True),
                },
                use_container_width=True,
                hide_index=True,
                key=spec_editor_key(code, is_water=True),
            )
            set_specs_df(code, edited_specs)
        st.caption(
            "Microbiological results are taken from the water micro protocol "
            "observations (Present / Absent)."
        )
    elif is_micro:
        if not is_initialized(code):
            set_widget_default("condition", code, "")
            set_widget_default("appearance", code, (header.appearance_text or "").strip())
            set_widget_default(
                "report_no",
                code,
                default_test_report_no(
                    selected, with_logo=default_report_with_logo(selected)
                ),
            )
            set_widget_default(
                "customer_sid",
                code,
                (selected.parameters or "").strip() or (selected.sample_name or ""),
            )
            set_widget_default("auth_signatory", code, default_authorized_signatory(report_settings))
            set_widget_default("checked_by", code, default_checked_by_analysts(selected))
            by_key = {r.test_key: r for r in results}
            keys = micro_report_keys_ordered(set(selected.selected_test_keys()) or set(by_key))
            set_specs_df(
                code,
                pd.DataFrame(
                    [
                        {
                            "Sr": spec_for_key(k).sr_no,
                            "Test": spec_for_key(k).name,
                            "Result": (by_key[k].result_value if k in by_key else "") or "",
                            "Limits": spec_for_key(k).limits,
                            "Method": spec_for_key(k).method,
                        }
                        for k in keys
                    ]
                ),
            )
            mark_initialized(code)

        p1, p2 = st.columns(2)
        with p1:
            st.markdown(
                f"**Name / address:**\n\n"
                f"{selected.customer_name or '—'}"
                f"{chr(10) + selected.customer_address if selected.customer_address else ''}"
            )
            st.markdown(f"**Sample:** {selected.sample_name or '—'}")
            st.markdown(f"**Lab code:** {selected.lab_code or selected.sample_code or '—'}")
        with p2:
            st.markdown(
                f"**Receipt date:** "
                f"{header.sample_received_on.strftime('%d/%m/%Y') if header.sample_received_on else '—'}"
            )
            st.markdown(
                f"**Analysis date:** "
                f"{format_analysis_date_range(header.date_of_analysis_from, header.date_of_analysis_to, legacy_single=header.date_of_analysis) or '—'}"
            )
            st.markdown(f"**Quantity:** {selected.quantity or '—'}")

        m1, m2 = st.columns(2)
        with m1:
            st.text_input("Condition of Sample", key=cond_key)
            st.text_input("Sample Appearance", key=appearance_key)
            st.text_input("Customer Sample ID", key=customer_sid_key)
        with m2:
            st.text_input("Report No", key=report_no_key)

        specs_df = get_specs_df(code)
        if not specs_df.empty:
            st.markdown("**Microbiological Test — results (limits & methods are fixed)**")
            st.dataframe(
                specs_df,
                use_container_width=True,
                hide_index=True,
            )
        st.caption(
            "Name of Test, Limits, and Method of Analysis are fixed for all Micro samples. "
            "Only Results come from the analyst."
        )
    else:
        preview = build_test_report_data(selected, header, results)
        report_defaults = default_reviewer_report_fields(selected, header)
        if not is_initialized(code):
            set_widget_default("condition", code, "")
            set_widget_default("tests_processed", code, preview.tests_processed)
            set_widget_default("ulr", code, report_defaults["ulr"])
            set_widget_default("report_date", code, report_defaults["report_date"])
            set_widget_default("customer_addr", code, report_defaults["customer_addr"])
            set_widget_default("customer_sid", code, report_defaults["customer_sid"])
            set_widget_default("batch_no", code, report_defaults["batch_no"])
            set_widget_default("lab_code", code, report_defaults["lab_code"])
            set_widget_default("location", code, "--")
            set_widget_default(
                "sampling_method",
                code,
                "Laboratory sampling" if selected.sampling_by_lab else "--",
            )
            set_widget_default("auth_signatory", code, default_authorized_signatory(report_settings))
            set_widget_default("checked_by", code, default_checked_by_analysts(selected))
            set_widget_default("remark", code, report_settings.default_remark_text)
            set_widget_default(
                "disclaimer",
                code,
                "\n".join(report_settings.disclaimer_bullets),
            )
            set_specs_df(
                code,
                pd.DataFrame(
                    [
                        {
                            "Sr": row.sr_no,
                            "Test": row.test_name,
                            "Result": row.result or "",
                            "Specification": row.specification or "",
                            "Method": row.method or "",
                        }
                        for row in preview.rows
                    ]
                ),
            )
            mark_initialized(code)

        p1, p2 = st.columns(2)
        with p1:
            st.markdown(f"**Sample:** {preview.sample_name or '—'}")
        with p2:
            st.markdown(f"**Receipt date:** {preview.date_of_sample_receipt or '—'}")
            st.markdown(f"**Analysis date:** {preview.test_performance_date or '—'}")
            st.markdown(f"**Quantity:** {preview.sample_quantity or '—'}")

        st.text_area(
            "Customer name & address",
            key=customer_addr_key,
            height=100,
            help="From reception CTR; editable before generating the Word report.",
        )
        f1, f2 = st.columns(2)
        with f1:
            st.text_input("Customer Sample ID", key=customer_sid_key)
            st.text_input("Batch No.", key=batch_no_key)
            st.text_input("Lab Code", key=lab_code_key)
        with f2:
            st.date_input("Report date", key=report_date_key, format="DD/MM/YYYY")
            st.text_input(
                "ULR No",
                key=ulr_key,
                help=(
                    f"Auto-generated from lab code ({ULR_TOTAL_LENGTH}-character ULR, "
                    "e.g. TC1611826000030601F). Edit if needed."
                ),
            )

        st.text_input(
            "Condition of Sample",
            key=cond_key,
            help="Printed on the final report. Enter before generating.",
        )
        st.text_input(
            "Tests processed",
            key=tests_key,
            help="Printed on the final report (default: As per customer request).",
        )
        m1, m2 = st.columns(2)
        with m1:
            st.text_input("Location of sampling", key=loc_key)
        with m2:
            st.text_input("Sampling Method", key=samp_method_key)
        st.text_area(
            "Remark (optional override)",
            key=remark_key,
            height=100,
            help="Leave as default or edit before generating.",
        )
        st.text_area(
            "Disclaimer bullets (optional override, one per line)",
            key=disclaimer_key,
            height=140,
            help="Supervisor defaults from Admin; edit here for this report only.",
        )

        if preview.rows:
            st.markdown("**Test results and specifications**")
            specs_df = get_specs_df(code)
            edited_specs = st.data_editor(
                specs_df,
                column_config={
                    "Sr": st.column_config.NumberColumn("Sr", disabled=True),
                    "Test": st.column_config.TextColumn("Test", disabled=True),
                    "Result": st.column_config.TextColumn("Result", disabled=True),
                    "Specification": st.column_config.TextColumn("Specification"),
                    "Method": st.column_config.TextColumn("Method", disabled=True),
                },
                use_container_width=True,
                hide_index=True,
                key=spec_editor_key(code, is_water=False),
            )
            set_specs_df(code, edited_specs)

    analyst_checked = default_checked_by_analysts(selected)
    s1, s2 = st.columns(2)
    with s1:
        st.selectbox(
            "Authorized signatory",
            options=signatory_options,
            key=auth_key,
        )
    with s2:
        st.text_input(
            "Checked by (assigned analyst)",
            value=analyst_checked,
            disabled=True,
            help=(
                "Filled from the analyst assigned at reception. "
                "Each analyst signs on the printed report."
            ),
        )
        set_widget("checked_by", code, analyst_checked)

    reviewer_note = st.text_input(
        "Reviewer note (optional, stored in analyst remarks)",
        key="reviewer_note",
    )

    if st.button("Generate Final Report", type="primary", key="gen_final_report"):
        try:
            gen_by = actor_display_name(actor)
            gen_at = format_stamp_datetime(now_lab())
            params = build_generation_params(
                selected,
                is_water=is_water,
                is_micro=is_micro,
                specs_df=get_specs_df(code),
                sample_code=code,
                report_settings=report_settings,
                generated_by=gen_by,
                generated_at=gen_at,
                get_field=get_widget,
            )
            output = generate_reviewer_final_report(
                selected,
                header,
                results,
                params,
            )
            note = (reviewer_note or "").strip()
            remarks = selected.analyst_remarks or ""
            if note:
                remarks = (remarks + "\n" if remarks else "") + f"[Reviewer] {note}"
            update_status(selected.sample_code, "reported", remarks, actor=actor)
            log_from_user(
                actor,
                "report.final",
                "request_samples",
                selected.sample_code,
            )
            st.session_state["reviewer_report_for"] = selected.sample_code
            st.session_state["reviewer_report_is_water"] = output.is_water
            st.session_state["reviewer_report_is_micro"] = output.is_micro
            st.session_state["reviewer_docx_bytes"] = output.docx_bytes
            st.session_state["reviewer_docx_name"] = output.docx_filename
            st.session_state["reviewer_pdf_bytes"] = output.pdf_bytes
            st.session_state["reviewer_pdf_name"] = output.pdf_filename or suggest_test_report_filename(selected)
            st.success(
                "Final report generated. Sample status set to **reported**. "
                "Download below. (Checked by — sign with pen on the printed report.)"
            )
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    if st.session_state.get("reviewer_report_for") == selected.sample_code:
        if st.session_state.get("reviewer_docx_bytes"):
            st.download_button(
                f"Download Word report ({st.session_state.get('reviewer_docx_name', 'report.docx')})",
                data=st.session_state["reviewer_docx_bytes"],
                file_name=st.session_state.get("reviewer_docx_name", "TestReport.docx"),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_final_report_docx",
            )
        pdf_bytes = st.session_state.get("reviewer_pdf_bytes")
        if pdf_bytes:
            st.download_button(
                f"Download PDF report ({st.session_state.get('reviewer_pdf_name', 'report.pdf')})",
                data=pdf_bytes,
                file_name=st.session_state.get("reviewer_pdf_name", "TestReport.pdf"),
                mime="application/pdf",
                use_container_width=True,
                key="dl_final_report_pdf",
            )
        elif st.session_state.get("reviewer_report_is_water") or st.session_state.get(
            "reviewer_report_is_micro"
        ):
            st.info(
                "Word report is ready. PDF conversion uses Microsoft Word on "
                "Windows or LibreOffice headless on Linux/Docker."
            )


main()
