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
from services.samples import (  # noqa: E402
    SEARCH_BY,
    SampleRecord,
    get_by_code,
    list_open,
    search_open,
    update_status,
)
from services.test_report_pdf import (  # noqa: E402
    build_test_report_data,
    generate_test_report_pdf_bytes,
    suggest_test_report_filename,
)
from ui.auth import require_role  # noqa: E402
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
    require_role("admin", "reviewer")
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

    preview = build_test_report_data(selected, header, results)
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
        st.markdown(f"**Tests:** {preview.tests_processed or '—'}")

    if preview.rows:
        st.dataframe(
            [
                {
                    "Sr": row.sr_no,
                    "Test": row.test_name,
                    "Result": row.result or "—",
                    "Specification": row.specification or "—",
                    "Method": row.method or "—",
                }
                for row in preview.rows
            ],
            use_container_width=True,
            hide_index=True,
        )

    reviewer_note = st.text_input(
        "Reviewer note (optional, stored in analyst remarks)",
        key="reviewer_note",
    )

    if st.button("Generate Final Report", type="primary", key="gen_final_report"):
        try:
            gen_by = actor_display_name(actor)
            gen_at = format_stamp_datetime(now_lab())
            report_bytes = generate_test_report_pdf_bytes(
                selected,
                header,
                results,
                generated_by=gen_by,
                generated_at=gen_at,
            )
            report_name = suggest_test_report_filename(selected)
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
            st.session_state["reviewer_pdf_bytes"] = report_bytes
            st.session_state["reviewer_pdf_name"] = report_name
            st.session_state["reviewer_pdf_for"] = selected.sample_code
            st.success(
                "Final report generated. Sample status set to **reported**. "
                "Download below. (Checked by — sign with pen on the printed PDF.)"
            )
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    if st.session_state.get("reviewer_pdf_bytes"):
        st.download_button(
            f"Download {st.session_state.get('reviewer_pdf_name', 'TestReport.pdf')}",
            data=st.session_state["reviewer_pdf_bytes"],
            file_name=st.session_state.get("reviewer_pdf_name", "TestReport.pdf"),
            mime="application/pdf",
            use_container_width=True,
            key="dl_final_report",
        )


main()
