"""
pages/1_Reception.py
--------------------
Reception workspace: sample packages, customer master, new intake, and edits.

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
    now_lab,
)
from services.auth import get_session_user  # noqa: E402
from services.requests import (  # noqa: E402
    get_test_request,
    search_test_requests,
    update_test_request,
    validate_request,
    validation_warnings,
)
from services.samples import delete_expired_samples  # noqa: E402
from ui.auth import require_page_access  # noqa: E402
from ui.components import (  # noqa: E402
    RECEPTION_TAB_CUSTOMERS,
    RECEPTION_TAB_EDIT,
    RECEPTION_TAB_NEW,
    RECEPTION_TAB_REGISTRATION,
    RECEPTION_TABS,
    apply_request_prefill,
    collect_form,
    inject_styles,
    mark_reception_tab,
    render_db_status,
    render_hero,
    render_section_title,
    require_edit_reason,
)
from ui.customer_master_panel import render_customer_master_panel  # noqa: E402
from ui.new_sample_registration_panel import render_new_sample_registration_panel  # noqa: E402
from ui.reception_save import render_ctr_downloads  # noqa: E402
from ui.test_packages_panel import render_test_packages_panel  # noqa: E402

st.set_page_config(
    page_title="S Testing Laboratory — Reception",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
        actor=actor,
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

    render_ctr_downloads(saved, actor, gen_by, gen_at)


def main() -> None:
    require_page_access("reception")
    actor = get_session_user()

    inject_styles()
    render_hero(
        title="Reception — Sample & customer intake",
        subtitle=(
            "Register test packages, maintain customers, receive new samples, "
            "or edit existing requests. Changes to existing data require a "
            "written reason and are versioned."
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

    tab_reg, tab_cust, tab_new, tab_edit = st.tabs(list(RECEPTION_TABS))

    with tab_reg:
        mark_reception_tab(RECEPTION_TAB_REGISTRATION)
        render_test_packages_panel(actor)

    with tab_cust:
        mark_reception_tab(RECEPTION_TAB_CUSTOMERS)
        render_customer_master_panel(actor)

    with tab_new:
        mark_reception_tab(RECEPTION_TAB_NEW)
        render_new_sample_registration_panel(actor)

    with tab_edit:
        mark_reception_tab(RECEPTION_TAB_EDIT)
        _edit_request_flow(actor)


main()
