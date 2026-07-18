"""
pages/1_Reception.py
--------------------
Reception workspace: Customer Test Request intake.

Saves permanent customer + request, creates one DB row per sample with an
auto sample_code and tests_to_perform, then offers PDF/DOCX download.
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
from services.docx_filler import fill_docx_bytes, suggest_docx_filename  # noqa: E402
from services.pdf_generator import generate_pdf_bytes, suggest_pdf_filename  # noqa: E402
from services.requests import save_test_request, validate_request  # noqa: E402
from services.samples import delete_expired_samples  # noqa: E402
from ui.auth import require_role  # noqa: E402
from ui.components import (  # noqa: E402
    collect_form,
    customer_picker,
    inject_styles,
    render_db_status,
    render_hero,
    render_section_title,
)

st.set_page_config(
    page_title="S Testing Laboratory — Reception",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    require_role("admin", "reception")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Reception — Customer Test Request",
        subtitle=(
            "Capture customer & sample intake. Each sample receives a unique "
            "<b>sample code</b> for the analyst (kept 10 days)."
        ),
        badge="Reception desk",
    )

    ok, msg = test_connection()
    render_db_status(ok, msg)
    st.write("")
    if not ok:
        st.error("Database not connected. Start Docker Postgres, then refresh.")
        st.stop()

    # Session cleanup of expired samples
    if not st.session_state.get("_reception_purged"):
        try:
            delete_expired_samples(actor=actor)
        except Exception:  # noqa: BLE001
            pass
        st.session_state["_reception_purged"] = True

    selected_customer = customer_picker()
    st.divider()

    data = collect_form(selected_customer)
    if data is None:
        st.caption(
            "Tip: fill at least one sample with a name and tests to perform. "
            "After save, sample codes appear for analyst handoff."
        )
        return

    errors = validate_request(data)
    if errors:
        st.error("Please fix the following before saving:")
        for e in errors:
            st.write(f"• {e}")
        return

    gen_by = actor_display_name(actor)
    gen_at = format_stamp_datetime(now_lab())

    try:
        with st.spinner("Saving customer, request & sample codes…"):
            saved = save_test_request(data, actor=actor)

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
        st.error(f"Save / generate failed: {exc}")
        st.info(
            "If you see a column error, run the migration:\n\n"
            "`docker exec -i sls_lab_db psql -U sls_user -d sls_lab "
            "< scripts/migrate_samples.sql`"
        )
        return

    render_section_title("5. Saved — sample codes & downloads")
    st.success(
        f"Request saved (ID #{saved.request_id}). "
        f"Customer ID #{saved.customer.id} (GST {saved.customer.gst_number})."
    )

    # Sample code handoff table for reception labels
    if saved.samples:
        render_section_title(
            "Sample codes for analyst",
            "Write these codes on sample labels. Analyst opens them in the Analyst page.",
        )
        code_rows = [
            {
                "Sample code": s.sample_code,
                "Sr.": s.sr_no,
                "Name of sample": s.sample_name,
                "Batch": s.batch_code,
                "Qty": s.quantity,
                "Tests to perform": s.parameters,
            }
            for s in saved.samples
        ]
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


main()
