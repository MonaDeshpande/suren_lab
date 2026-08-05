"""
pages/3_Reviewer.py
-------------------
Reviewer workspace:

1. Find sample (lab code / sample / client) within 10-day window
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
from services.audit import (  # noqa: E402
    actor_display_name,
    format_stamp_datetime,
    log_from_user,
    now_lab,
)
from services.auth import get_session_user  # noqa: E402
from services.protocol_store import get_protocol_header, list_results  # noqa: E402
from services.protocols.test_catalog import (  # noqa: E402
    CATEGORY_MICRO,
    CATEGORY_WATER,
    normalize_category,
)
from services.samples import (  # noqa: E402
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITH_LOGO,
    SampleRecord,
    SEARCH_BY,
    get_by_code,
    list_open,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
    report_format_label,
    search_open,
    update_status,
)
from services.test_report_micro_docx import MicroReportFillOptions  # noqa: E402
from services.test_report_pdf import (  # noqa: E402
    build_test_report_data,
    generate_final_report,
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
from services.water_report_catalog import WaterReportLimits  # noqa: E402
from ui.auth import require_page_access  # noqa: E402
from ui.components import (  # noqa: E402
    inject_styles,
    render_db_status,
    render_hero,
    render_section_title,
)

st.set_page_config(
    page_title="S Testing Laboratory — Reviewer",
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
                st.info("No matching samples in the 10-day window.")

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
                f"{header.date_of_analysis.isoformat() if header.date_of_analysis else '—'}"
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
    fields_key = "reviewer_report_fields_for"
    cond_key = f"reviewer_condition_{selected.sample_code}"
    tests_key = f"reviewer_tests_processed_{selected.sample_code}"
    spec_key = f"reviewer_specs_{selected.sample_code}"
    appearance_key = f"reviewer_appearance_{selected.sample_code}"
    testing_at_key = f"reviewer_testing_at_{selected.sample_code}"
    ulr_key = f"reviewer_ulr_{selected.sample_code}"
    report_chem_key = f"reviewer_report_chem_{selected.sample_code}"
    report_micro_key = f"reviewer_report_micro_{selected.sample_code}"
    report_no_key = f"reviewer_report_no_{selected.sample_code}"
    customer_sid_key = f"reviewer_customer_sid_{selected.sample_code}"

    if is_water:
        if st.session_state.get(fields_key) != selected.sample_code:
            st.session_state[fields_key] = selected.sample_code
            st.session_state[cond_key] = ""
            st.session_state[appearance_key] = (header.appearance_text or "").strip()
            st.session_state[testing_at_key] = DEFAULT_TESTING_CONDUCTED_AT
            st.session_state[ulr_key] = ""
            base = (selected.lab_code or selected.sample_code or "").strip().rstrip("/")
            st.session_state[report_chem_key] = f"{base}/01" if base else ""
            st.session_state[report_micro_key] = f"{base}/02" if base else ""
            st.session_state[customer_sid_key] = (
                (selected.parameters or "").strip() or "Drinking Water"
            )
            st.session_state[spec_key] = pd.DataFrame(build_water_report_limit_rows(selected, results))

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
                f"{header.date_of_analysis.strftime('%d/%m/%Y') if header.date_of_analysis else '—'}"
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

        if not st.session_state[spec_key].empty:
            st.markdown("**Test results and IS 10500 limits**")
            edited_specs = st.data_editor(
                st.session_state[spec_key],
                column_config={
                    "Test": st.column_config.TextColumn("Test key", disabled=True),
                    "Result": st.column_config.TextColumn("Result", disabled=True),
                    "Desirable Limit": st.column_config.TextColumn("Desirable Limit"),
                    "Permissible limit": st.column_config.TextColumn("Permissible limit"),
                    "Method": st.column_config.TextColumn("Method", disabled=True),
                },
                use_container_width=True,
                hide_index=True,
                key=f"reviewer_water_spec_editor_{selected.sample_code}",
            )
            st.session_state[spec_key] = edited_specs
        st.caption(
            "Microbiological section is included with blank results until the "
            "water micro protocol is added."
        )
    elif is_micro:
        if st.session_state.get(fields_key) != selected.sample_code:
            st.session_state[fields_key] = selected.sample_code
            st.session_state[cond_key] = ""
            st.session_state[appearance_key] = (header.appearance_text or "").strip()
            base = (selected.lab_code or selected.sample_code or "").strip().rstrip("/")
            st.session_state[report_no_key] = f"{base}/01" if base else ""
            st.session_state[customer_sid_key] = (selected.parameters or "").strip() or (
                selected.sample_name or ""
            )
            by_key = {r.test_key: r for r in results}
            keys = micro_report_keys_ordered(set(selected.selected_test_keys()) or set(by_key))
            st.session_state[spec_key] = pd.DataFrame(
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
            )

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
                f"{header.date_of_analysis.strftime('%d/%m/%Y') if header.date_of_analysis else '—'}"
            )
            st.markdown(f"**Quantity:** {selected.quantity or '—'}")

        m1, m2 = st.columns(2)
        with m1:
            st.text_input("Condition of Sample", key=cond_key)
            st.text_input("Sample Appearance", key=appearance_key)
            st.text_input("Customer Sample ID", key=customer_sid_key)
        with m2:
            st.text_input("Report No", key=report_no_key)

        if not st.session_state[spec_key].empty:
            st.markdown("**Microbiological Test — results (limits & methods are fixed)**")
            st.dataframe(
                st.session_state[spec_key],
                use_container_width=True,
                hide_index=True,
            )
        st.caption(
            "Name of Test, Limits, and Method of Analysis are fixed for all Micro samples. "
            "Only Results come from the analyst."
        )
    else:
        preview = build_test_report_data(selected, header, results)
        if st.session_state.get(fields_key) != selected.sample_code:
            st.session_state[fields_key] = selected.sample_code
            st.session_state[cond_key] = ""
            st.session_state[tests_key] = preview.tests_processed
            st.session_state[spec_key] = pd.DataFrame(
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
            )

        p1, p2 = st.columns(2)
        with p1:
            st.markdown(f"**Name / address:**\n\n{preview.customer_name_address or '—'}")
            st.markdown(f"**Sample:** {preview.sample_name or '—'}")
            st.markdown(f"**Batch:** {preview.batch_no or '—'}")
            st.markdown(f"**Lab code:** {preview.lab_code or '—'}")
        with p2:
            st.markdown(f"**Receipt date:** {preview.date_of_sample_receipt or '—'}")
            st.markdown(f"**Analysis date:** {preview.test_performance_date or '—'}")
            st.markdown(f"**Quantity:** {preview.sample_quantity or '—'}")

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

        if preview.rows:
            st.markdown("**Test results and specifications**")
            edited_specs = st.data_editor(
                st.session_state[spec_key],
                column_config={
                    "Sr": st.column_config.NumberColumn("Sr", disabled=True),
                    "Test": st.column_config.TextColumn("Test", disabled=True),
                    "Result": st.column_config.TextColumn("Result", disabled=True),
                    "Specification": st.column_config.TextColumn("Specification"),
                    "Method": st.column_config.TextColumn("Method", disabled=True),
                },
                use_container_width=True,
                hide_index=True,
                key=f"reviewer_spec_editor_{selected.sample_code}",
            )
            st.session_state[spec_key] = edited_specs

    reviewer_note = st.text_input(
        "Reviewer note (optional, stored in analyst remarks)",
        key="reviewer_note",
    )

    if st.button("Generate Final Report", type="primary", key="gen_final_report"):
        try:
            gen_by = actor_display_name(actor)
            gen_at = format_stamp_datetime(now_lab())
            specification_by_test_name: dict[str, str] = {}
            limit_overrides: dict[str, WaterReportLimits] = {}
            specs_df = st.session_state.get(spec_key)
            if specs_df is not None and not specs_df.empty:
                if is_water:
                    for _, row in specs_df.iterrows():
                        key = str(row["Test"])
                        limit_overrides[key] = WaterReportLimits(
                            desirable=str(row.get("Desirable Limit", "") or ""),
                            permissible=str(row.get("Permissible limit", "") or ""),
                        )
                elif not is_micro:
                    for _, row in specs_df.iterrows():
                        specification_by_test_name[str(row["Test"])] = str(
                            row.get("Specification", "") or ""
                        )

            water_opts = None
            micro_opts = None
            if is_water:
                water_opts = WaterReportFillOptions(
                    ulr_no=st.session_state.get(ulr_key, ""),
                    report_no_chemical=st.session_state.get(report_chem_key, ""),
                    report_no_micro=st.session_state.get(report_micro_key, ""),
                    condition_of_sample=st.session_state.get(cond_key, ""),
                    customer_sample_id=st.session_state.get(customer_sid_key, ""),
                    sample_appearance=st.session_state.get(appearance_key, ""),
                    testing_conducted_at=st.session_state.get(testing_at_key, ""),
                    limit_overrides=limit_overrides,
                    generated_by=gen_by,
                    generated_at=gen_at,
                )
            elif is_micro:
                micro_opts = MicroReportFillOptions(
                    report_no=st.session_state.get(report_no_key, ""),
                    condition_of_sample=st.session_state.get(cond_key, ""),
                    customer_sample_id=st.session_state.get(customer_sid_key, ""),
                    sample_appearance=st.session_state.get(appearance_key, ""),
                    generated_by=gen_by,
                    generated_at=gen_at,
                )

            output = generate_final_report(
                selected,
                header,
                results,
                generated_by=gen_by,
                generated_at=gen_at,
                condition_of_sample=st.session_state.get(cond_key, ""),
                tests_processed=(
                    st.session_state.get(tests_key, "")
                    if not is_water and not is_micro
                    else None
                ),
                specification_by_test_name=(
                    specification_by_test_name or None
                    if not is_water and not is_micro
                    else None
                ),
                water_opts=water_opts,
                micro_opts=micro_opts,
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
        elif st.session_state.get("reviewer_report_is_water"):
            st.info(
                "Word report is ready. PDF conversion requires Microsoft Word "
                "(docx2pdf) on this machine."
            )


main()
