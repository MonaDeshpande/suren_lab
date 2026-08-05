"""
ui/components.py
----------------
Reusable Streamlit UI building blocks for the Customer Test Request form.

Keeping widgets here keeps app.py focused on page flow / orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from services.customers import (
    MAX_CONTACTS,
    ContactPerson,
    Customer,
    get_customer_by_gst,
    get_customer_by_id,
    gst_ready_for_lookup,
    search_customers,
)
from services.requests import SampleRow, TestRequestData, assign_derived_sample_codes
from services.versions import validate_edit_reason


# Path to the CSS file next to this module
STYLES_PATH = Path(__file__).resolve().parent / "styles.css"


@st.cache_data(ttl=60)
def _cached_resolve_package_tests(
    sample_name: str,
    ptype: str,
    category: str,
):
    """Cache package resolution across fragment reruns."""
    from services.test_packages import resolve_package_tests

    return resolve_package_tests(sample_name, ptype, category=category)


def _package_panel_select_label(
    pkg_id: int,
    product: str,
    type_label: str,
    version: int,
    wl_count: int,
    nwl_count: int,
) -> str:
    """Match label format used in ui/test_packages_panel.py selectboxes."""
    return (
        f"#{pkg_id} — {product} — {type_label} "
        f"(v{version}, WL:{wl_count} / NWL:{nwl_count})"
    )


def _render_food_sample_package_block(
    *,
    sr_no: int,
    sample_name: str,
    ptype: str,
    filter_category: str,
    pinned_package_id: Optional[int] = None,
    pinned_version_no: Optional[int] = None,
    custom_count: int = 0,
) -> None:
    """Show package defined/not-defined status and optional intake vs active version."""
    from services.protocols.test_catalog import CATEGORY_FOOD, get_test, normalize_category
    from services.test_packages import (
        describe_sample_package,
        get_package,
        package_type_label,
    )

    if normalize_category(filter_category) != CATEGORY_FOOD:
        return

    desc = describe_sample_package(
        sample_name,
        ptype,
        category=filter_category,
        pinned_package_id=pinned_package_id,
        pinned_version_no=pinned_version_no,
    )
    status = desc["status"]
    extra = f" + {custom_count} custom" if custom_count else ""

    st.markdown(f"**Sr. {sr_no} — Package assignment**")

    if status == "defined":
        pkg_id = desc["package_id"]
        wl_names = ", ".join(
            get_test(k).name for k in desc["test_keys_with_logo"]
        )
        nwl_names = ", ".join(
            get_test(k).name for k in desc["test_keys_without_logo"]
        )
        st.success(
            f"**Defined** — #{pkg_id} **{desc['display_label']}** "
            f"(v{desc['version_no']}, active){extra} — "
            f"WL: {desc['wl_count']} ({wl_names or '—'}); "
            f"NWL: {desc['nwl_count']} ({nwl_names or '—'})"
        )
        if not desc["test_keys_without_logo"]:
            st.warning(
                f"Sr. {sr_no}: this package has **no without-logo (NWL) tests**. "
                "Report format **B — Without Logo** or **Both** needs a separate "
                "NWL list — edit the package under **Test packages**."
            )
    elif status == "inactive":
        pkg_id = desc["package_id"]
        st.warning(
            f"**Inactive** — #{pkg_id} **{desc['display_label']}** "
            f"(v{desc['version_no']}) exists but is deactivated. "
            f"Activate it under **Test packages** before saving this sample."
        )
    else:
        st.warning(
            f"**Not defined** — no package for **{sample_name}** — "
            f"{package_type_label(ptype)}. Create it under **Test packages**."
        )

    if pinned_package_id is not None and pinned_version_no is not None:
        st.caption(
            f"**Intake package:** #{pinned_package_id} v{pinned_version_no}"
        )
        if desc.get("version_mismatch") and desc.get("version_no") is not None:
            st.info(
                f"**Current active:** v{desc['version_no']}. "
                "Saving a pending row will use the current active package version."
            )

    manage_id = desc.get("package_id") or pinned_package_id
    if manage_id:
        pkg = get_package(int(manage_id))
        if pkg is not None:
            select_label = _package_panel_select_label(
                pkg.id,
                pkg.sample_product_name,
                pkg.package_type_label,
                pkg.current_version_no,
                len(pkg.test_keys_with_logo),
                len(pkg.test_keys_without_logo),
            )
            if st.button(
                "Manage package in Test packages",
                key=f"pkg_manage_{sr_no}",
            ):
                st.session_state["reception_mode"] = "Test packages"
                st.session_state["pkg_edit_select"] = select_label
                st.rerun()


@st.cache_data(ttl=60)
def _cached_custom_formulas_for_scope(category: str, ptype_key: str):
    """Cache custom formula lists across fragment reruns."""
    from services.custom_formulas import custom_formulas_for_scope

    ptype = ptype_key or None
    return tuple(custom_formulas_for_scope(category, ptype))


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
    """Top brand banner for the food testing lab (title only; logo is for PDF/Word)."""
    st.markdown(
        f"""
        <div class="sls-hero">
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


def _refresh_customer_search() -> None:
    """Run customer master search from the Section 1 lookup box."""
    query = str(st.session_state.get("customer_search_q") or "")
    try:
        st.session_state["customer_search_results"] = search_customers(query)
        st.session_state.pop("customer_search_error", None)
    except Exception as exc:  # noqa: BLE001
        st.session_state["customer_search_error"] = str(exc)
        st.session_state["customer_search_results"] = []


def _push_customer_to_session(
    customer: Customer,
    *,
    autoload_msg: str | None = None,
) -> None:
    """Write permanent customer fields into CTR widget session keys."""
    selected_key = customer.id if customer.id is not None else "new"
    st.session_state["_prefill_customer_key"] = selected_key
    st.session_state["f_customer_name"] = customer.customer_name
    st.session_state["f_address"] = customer.address
    st.session_state["f_contact_number"] = customer.contact_number
    st.session_state["f_gst_number"] = customer.gst_number
    st.session_state["_gst_autoload_last"] = (customer.gst_number or "").strip().upper()
    _sync_contacts_prefill(customer)
    if autoload_msg:
        st.session_state["customer_gst_autoload_msg"] = autoload_msg
    else:
        st.session_state.pop("customer_gst_autoload_msg", None)


def _on_gst_lookup() -> None:
    """Auto-load permanent customer when a full GSTIN is entered in Section 3."""
    gst_raw = str(st.session_state.get("f_gst_number") or "").strip()
    gst_norm = gst_raw.upper()
    if not gst_ready_for_lookup(gst_raw):
        if gst_norm != st.session_state.get("_gst_autoload_last"):
            st.session_state.pop("customer_gst_autoload_msg", None)
        return

    if gst_norm == st.session_state.get("_gst_autoload_last"):
        return

    try:
        existing = get_customer_by_gst(gst_raw)
    except Exception:  # noqa: BLE001
        st.session_state.pop("customer_gst_autoload_msg", None)
        return

    if existing is None:
        st.session_state["_gst_autoload_last"] = gst_norm
        st.session_state.pop("customer_gst_autoload_msg", None)
        return

    _push_customer_to_session(
        existing,
        autoload_msg=f"Loaded existing customer: {existing.customer_name}",
    )


def _resolved_customer_id(prefill: Customer, gst_number: str) -> Optional[int]:
    """Customer id for save — picker/GST autoload store id in session keys."""
    prefill_key = st.session_state.get("_prefill_customer_key")
    if isinstance(prefill_key, int):
        return prefill_key
    if prefill.id is not None:
        return prefill.id
    if gst_ready_for_lookup(gst_number):
        try:
            existing = get_customer_by_gst(gst_number)
        except Exception:  # noqa: BLE001
            return None
        if existing and existing.id is not None:
            return existing.id
    return None


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
        "Search by GST or customer name — results update as you type. "
        "Or enter a full 15-character GST in Section 3 to auto-load saved details.",
    )

    query = st.text_input(
        "Search GST / customer name",
        placeholder="e.g. 27AAAAA0000A1Z5 or Acme Foods",
        key="customer_search_q",
        on_change=_refresh_customer_search,
    )

    prev_q = st.session_state.get("_customer_search_prev_q")
    if prev_q != query or "customer_search_results" not in st.session_state:
        st.session_state["_customer_search_prev_q"] = query
        _refresh_customer_search()

    search_error = st.session_state.get("customer_search_error")
    if search_error:
        st.warning(f"Could not search customers: {search_error}")

    results: list[Customer] = st.session_state.get("customer_search_results", [])
    if results:
        st.caption(
            f"{len(results)} customer(s) shown. Empty search lists recent customers."
        )

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


def _sync_contacts_prefill(prefill: Customer) -> None:
    """Keep up to five contact-person widget keys aligned with picker selection."""
    contacts = prefill.resolved_contacts()
    selected_key = prefill.id if prefill.id is not None else "new"
    contacts_key = f"contacts:{selected_key}"

    if st.session_state.get("_prefill_contacts_key") != contacts_key:
        st.session_state["_prefill_contacts_key"] = contacts_key
        st.session_state["ctr_contact_count"] = max(1, min(len(contacts), MAX_CONTACTS))
        for i in range(1, MAX_CONTACTS + 1):
            if i <= len(contacts):
                st.session_state[f"ctr_c{i}_name"] = contacts[i - 1].contact_name
                st.session_state[f"ctr_c{i}_email"] = contacts[i - 1].email
            else:
                st.session_state[f"ctr_c{i}_name"] = ""
                st.session_state[f"ctr_c{i}_email"] = ""

    st.session_state.setdefault("ctr_contact_count", 1)
    for i in range(1, MAX_CONTACTS + 1):
        default_name = contacts[i - 1].contact_name if i <= len(contacts) else ""
        default_email = contacts[i - 1].email if i <= len(contacts) else ""
        st.session_state.setdefault(f"ctr_c{i}_name", default_name)
        st.session_state.setdefault(f"ctr_c{i}_email", default_email)


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
        if selected_key == "new":
            st.session_state["_prefill_customer_key"] = selected_key
            st.session_state["f_customer_name"] = p.customer_name
            st.session_state["f_address"] = p.address
            st.session_state["f_contact_number"] = p.contact_number
            st.session_state["f_gst_number"] = p.gst_number
            st.session_state.pop("_gst_autoload_last", None)
            st.session_state.pop("customer_gst_autoload_msg", None)
            _sync_contacts_prefill(p)
        else:
            _push_customer_to_session(p)

    # Ensure keys exist even on first run with no picker change
    for key, default in [
        ("f_customer_name", p.customer_name),
        ("f_address", p.address),
        ("f_contact_number", p.contact_number),
        ("f_gst_number", p.gst_number),
    ]:
        st.session_state.setdefault(key, default)

    _sync_contacts_prefill(p)

    return p


def _render_contact_controls() -> int:
    """Add/remove contact rows (max five). Returns active contact count."""
    count = int(st.session_state.get("ctr_contact_count", 1))
    count = max(1, min(count, MAX_CONTACTS))
    st.session_state["ctr_contact_count"] = count

    btn_add, btn_remove, _ = st.columns([1, 1, 4])
    with btn_add:
        if st.button(
            "Add contact person",
            disabled=count >= MAX_CONTACTS,
            use_container_width=True,
            key="ctr_add_contact",
        ):
            st.session_state["ctr_contact_count"] = count + 1
            st.rerun()
    with btn_remove:
        if st.button(
            "Remove last contact",
            disabled=count <= 1,
            use_container_width=True,
            key="ctr_remove_contact",
        ):
            st.session_state[f"ctr_c{count}_name"] = ""
            st.session_state[f"ctr_c{count}_email"] = ""
            st.session_state["ctr_contact_count"] = count - 1
            st.rerun()

    st.caption(
        f"Contact persons: {count} of {MAX_CONTACTS} max. "
        "Each may have a different name and email."
    )
    return count


def _read_contacts_from_session(count: int) -> list[ContactPerson]:
    contacts: list[ContactPerson] = []
    for i in range(1, count + 1):
        contacts.append(
            ContactPerson(
                position=i,
                contact_name=str(st.session_state.get(f"ctr_c{i}_name", "") or ""),
                email=str(st.session_state.get(f"ctr_c{i}_email", "") or ""),
            )
        )
    return contacts


def edit_reason_field(
    key: str = "edit_reason",
    *,
    label: str = "Reason for edit *",
    help_text: str = (
        "Required when changing existing customer or request data "
        "(minimum 10 characters)."
    ),
) -> str:
    """Render a mandatory edit-reason textarea."""
    return st.text_area(
        label,
        key=key,
        height=80,
        help=help_text,
        placeholder="Describe why this change is being made…",
    )


def require_edit_reason(reason: str) -> bool:
    """
    Show Streamlit error when edit reason is invalid.

    Returns True when valid, False after st.error (caller should return).
    """
    try:
        validate_edit_reason(reason)
        return True
    except ValueError as exc:
        st.error(str(exc))
        return False


def _bool_to_yn(value: Optional[bool]) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not specified"


_CTR_TABLE_COLUMNS = (
    "Sr. No",
    "Name of sample",
    "Code/batch no.",
    "Sample qty.",
    "Parameters",
    "_sample_id",
    "_status",
)
_CTR_TEXT_COLUMNS = (
    "Name of sample",
    "Code/batch no.",
    "Sample qty.",
    "Parameters",
    "_status",
)
_SAMPLE_EDITOR_KEY = "sample_editor"
_SAMPLE_EDITOR_WIDGET_KEY = "sample_editor_widget"
# data_editor's widget key stores EditingState (dict), not a DataFrame.
# Persist the editor return value here so Save (outside the fragment) can read it.
_SAMPLE_EDITOR_LIVE_KEY = "sample_editor_live"


def _default_sample_rows(count: int = 1) -> list[dict]:
    return [
        {
            "Sr. No": i,
            "Name of sample": "",
            "Code/batch no.": "",
            "Sample qty.": "",
            "Parameters": "",
            "_sample_id": None,
            "_status": "pending",
        }
        for i in range(1, count + 1)
    ]


def _cell_text(value: object) -> str:
    """Normalize editor cells so None/NaN never render as the literal 'None'."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text in {"None", "nan", "<NA>", "NaT"}:
        return ""
    return str(value) if not isinstance(value, str) else value


def _normalize_ctr_df(df: pd.DataFrame) -> pd.DataFrame:
    """Stable CTR table: fixed columns, empty strings instead of None/NaN."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(_default_sample_rows())

    out = df.copy()
    for col in _CTR_TABLE_COLUMNS:
        if col not in out.columns:
            if col == "Sr. No":
                out[col] = list(range(1, len(out) + 1))
            elif col == "_sample_id":
                out[col] = None
            elif col == "_status":
                out[col] = "pending"
            else:
                out[col] = ""

    for col in _CTR_TEXT_COLUMNS:
        out[col] = [_cell_text(v) for v in out[col].tolist()]

    sr_vals: list[int] = []
    for i, raw in enumerate(out["Sr. No"].tolist(), start=1):
        try:
            sr_vals.append(int(raw))
        except (TypeError, ValueError):
            sr_vals.append(i)
    out["Sr. No"] = sr_vals

    sample_ids: list[object] = []
    for raw in out["_sample_id"].tolist():
        if raw is None:
            sample_ids.append(None)
            continue
        try:
            if pd.isna(raw):
                sample_ids.append(None)
                continue
        except (TypeError, ValueError):
            pass
        try:
            sample_ids.append(int(raw))
        except (TypeError, ValueError):
            sample_ids.append(None)
    out["_sample_id"] = sample_ids

    return out.loc[:, list(_CTR_TABLE_COLUMNS)]


def _reset_sample_editor(df: pd.DataFrame) -> None:
    """Replace editor data and clear widget state so Streamlit remounts cleanly."""
    normalized = _normalize_ctr_df(df)
    st.session_state[_SAMPLE_EDITOR_KEY] = normalized
    st.session_state[_SAMPLE_EDITOR_LIVE_KEY] = normalized
    st.session_state.pop(_SAMPLE_EDITOR_WIDGET_KEY, None)


def _current_sample_editor_df() -> pd.DataFrame:
    """
    Read the live sample table without writeback loops.

    Prefer the DataFrame snapshot written after each data_editor render.
    The widget key holds EditingState (dict), not a DataFrame — do not treat
    it as table data. Writing editor output back into the same key used as
    `data=` makes cell edits disappear on Enter — see Streamlit #7749.
    """
    live = st.session_state.get(_SAMPLE_EDITOR_LIVE_KEY)
    if isinstance(live, pd.DataFrame):
        return _normalize_ctr_df(live)
    # Legacy / unexpected: some Streamlit builds may mirror a DataFrame.
    widget_val = st.session_state.get(_SAMPLE_EDITOR_WIDGET_KEY)
    if isinstance(widget_val, pd.DataFrame):
        return _normalize_ctr_df(widget_val)
    stored = st.session_state.get(_SAMPLE_EDITOR_KEY)
    if isinstance(stored, pd.DataFrame):
        return _normalize_ctr_df(stored)
    return pd.DataFrame(_default_sample_rows())


def _sample_row_nonempty(row: dict) -> bool:
    return any(
        _cell_text(row.get(col)).strip()
        for col in ("Name of sample", "Sample qty.", "Parameters")
    )


def _sample_code_preview_map(lab_code: str, sample_df: pd.DataFrame) -> dict[int, str]:
    """Preview derived sample IDs for non-empty rows (by Sr. No)."""
    from services.samples import derive_sample_code

    filled_sr: list[int] = []
    for row in sample_df.to_dict(orient="records"):
        if not _sample_row_nonempty(row):
            continue
        try:
            filled_sr.append(int(row.get("Sr. No") or 0))
        except (TypeError, ValueError):
            continue
    filled_sr.sort()
    total = len(filled_sr)
    return {
        sr_no: derive_sample_code(lab_code, index=index, total=total)
        for index, sr_no in enumerate(filled_sr, start=1)
    }


def _migrate_sample_editor_df(df: pd.DataFrame, category: str) -> pd.DataFrame:
    """Normalize legacy wide editor state to the 5-column CTR table."""
    from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category
    from services.samples import REPORT_FORMAT_LABELS, REPORT_FORMAT_WITH_LOGO

    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame(_default_sample_rows())

    if all(c in df.columns for c in _CTR_TABLE_COLUMNS) and "Category" not in df.columns:
        return _normalize_ctr_df(df)

    rows: list[dict] = []
    for _, row in df.iterrows():
        try:
            sr_no = int(row.get("Sr. No") or len(rows) + 1)
        except (TypeError, ValueError):
            sr_no = len(rows) + 1

        params = ""
        if _cell_text(row.get("Parameters")).strip():
            params = _cell_text(row.get("Parameters"))
        elif _cell_text(row.get("Test type")).strip():
            params = _cell_text(row.get("Test type"))
        elif normalize_category(category) != CATEGORY_FOOD:
            params = _cell_text(row.get("Parameters"))

        rows.append(
            {
                "Sr. No": sr_no,
                "Name of sample": _cell_text(row.get("Name of sample")),
                "Code/batch no.": _cell_text(row.get("Code/batch no.")),
                "Sample qty.": _cell_text(row.get("Sample qty.")),
                "Parameters": params,
                "_sample_id": row.get("_sample_id"),
                "_status": _cell_text(row.get("_status")) or "pending",
            }
        )

        if "Assigned analyst" in df.columns:
            st.session_state.setdefault(
                f"workflow_analyst_{sr_no}",
                _cell_text(row.get("Assigned analyst")),
            )
        if "Protocol No" in df.columns:
            st.session_state.setdefault(
                f"workflow_protocol_no_{sr_no}",
                _cell_text(row.get("Protocol No")),
            )
        if "Report format" in df.columns:
            fmt = _cell_text(row.get("Report format")).strip()
            st.session_state.setdefault(
                f"workflow_report_format_{sr_no}",
                fmt or REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
            )
        elif f"workflow_report_format_{sr_no}" not in st.session_state:
            st.session_state[f"workflow_report_format_{sr_no}"] = REPORT_FORMAT_LABELS[
                REPORT_FORMAT_WITH_LOGO
            ]

    return _normalize_ctr_df(
        pd.DataFrame(rows) if rows else pd.DataFrame(_default_sample_rows())
    )


def _sync_request_prefill(request: TestRequestData) -> None:
    """Push request header + sample table into session_state widget keys."""
    req_key = f"req:{request.request_id}"
    if st.session_state.get("_prefill_request_key") != req_key:
        st.session_state["_prefill_request_key"] = req_key
        st.session_state["f_request_date"] = request.request_date
        st.session_state["f_lab_code"] = request.lab_code or ""
        st.session_state["f_number_of_samples"] = (
            int(request.number_of_samples) if request.number_of_samples else 1
        )
        st.session_state["f_sampling_choice"] = _bool_to_yn(request.sampling_by_lab)
        st.session_state["f_decision_choice"] = _bool_to_yn(request.decision_rule)
        st.session_state["f_service_type"] = request.service_type or ""
        st.session_state["f_delivery_mode"] = request.delivery_mode or ""
        st.session_state["f_storage_temperature"] = request.storage_temperature or ""
        st.session_state["f_test_method_spec"] = request.test_method_spec or ""
        st.session_state["f_payment_details"] = request.payment_details or ""
        st.session_state["f_sample_description"] = request.sample_description or ""

        from services.protocols.test_catalog import (
            CATEGORY_FOOD,
            CATEGORY_MICRO,
            CATEGORY_WATER,
            SAMPLE_CATEGORIES,
            TEST_CATALOG,
            normalize_category,
        )
        from services.test_packages import package_type_label
        from services.samples import (
            REPORT_FORMAT_BOTH,
            REPORT_FORMAT_LABELS,
            REPORT_FORMAT_WITH_LOGO,
            normalize_report_format,
            report_format_label,
        )
        from services.users import analyst_display_label, list_active_analysts

        analysts = list_active_analysts()
        id_to_label = {u.id: analyst_display_label(u) for u in analysts}

        rows = []
        for s in request.samples:
            cat = normalize_category(s.category)
            if cat == CATEGORY_FOOD:
                params_val = package_type_label(getattr(s, "package_type", None))
            elif cat in (CATEGORY_WATER, CATEGORY_MICRO):
                params_val = ""
            else:
                params_val = s.parameters or ""
            rows.append(
                {
                    "Sr. No": s.sr_no,
                    "Name of sample": s.sample_name or "",
                    "Code/batch no.": s.batch_code or "",
                    "Sample qty.": s.quantity or "",
                    "Parameters": params_val,
                    "_sample_id": s.id,
                    "_status": s.status,
                }
            )
            st.session_state[f"workflow_analyst_{s.sr_no}"] = id_to_label.get(
                s.assigned_analyst_id, ""
            )
            st.session_state[f"workflow_protocol_no_{s.sr_no}"] = (
                getattr(s, "protocol_no", "") or ""
            )
            st.session_state[f"workflow_report_format_{s.sr_no}"] = report_format_label(
                s.report_format
            )
        if not rows:
            rows = _default_sample_rows()
        _reset_sample_editor(pd.DataFrame(rows))
        if request.samples:
            first_cat = request.samples[0].category
            st.session_state["sample_category_select"] = SAMPLE_CATEGORIES.get(
                first_cat, list(SAMPLE_CATEGORIES.values())[0]
            )
            for s in request.samples:
                pass  # logo test sets come from package at save time


def apply_request_prefill(request: TestRequestData) -> None:
    """Load a saved request into CTR form session keys before widgets render."""
    _sync_request_prefill(request)
    _sync_customer_prefill(request.customer)


def clear_ctr_form_state() -> None:
    """Remove CTR intake widget keys so a fresh form can be created."""
    prefixes = ("f_", "ctr_c", "workflow_", "custom_tests_sr_")
    exact = {
        "_prefill_request_key",
        "_prefill_customer_key",
        "_prefill_contacts_key",
        "_customer_search_prev_q",
        "_gst_autoload_last",
        "customer_gst_autoload_msg",
        "customer_search_error",
        "customer_search_q",
        "customer_search_results",
        "customer_select",
        "sample_category_select",
        "ctr_contact_count",
        _SAMPLE_EDITOR_KEY,
        _SAMPLE_EDITOR_LIVE_KEY,
        _SAMPLE_EDITOR_WIDGET_KEY,
    }
    for key in list(st.session_state.keys()):
        if key in exact or key.startswith(prefixes):
            st.session_state.pop(key, None)


def collect_form(
    prefill: Optional[Customer] = None,
    request_prefill: Optional[TestRequestData] = None,
    *,
    edit_mode: bool = False,
    submit_label: str = "Save & Generate Form",
) -> Optional[tuple[TestRequestData, str]]:
    """
    Render the main intake form and return data + edit reason on submit.

    Returns (TestRequestData, edit_reason) or None when not submitted.
    """
    from services.samples import (
        LABEL_TO_REPORT_FORMAT,
        REPORT_FORMAT_BOTH,
        REPORT_FORMAT_LABELS,
        REPORT_FORMAT_WITHOUT_LOGO,
        REPORT_FORMAT_WITH_LOGO,
    )
    from services.custom_formulas import custom_formula_select_label
    from services.protocols.test_catalog import (
        CATEGORY_FOOD,
        CATEGORY_MICRO,
        CATEGORY_WATER,
        SAMPLE_CATEGORIES,
        default_test_keys_for_category,
        get_test,
        normalize_category,
    )
    from services.test_packages import (
        PACKAGE_TYPE_LABELS,
        normalize_package_type,
        package_type_label,
    )

    report_format_options = list(REPORT_FORMAT_LABELS.values())
    test_type_options = [""] + PACKAGE_TYPE_LABELS

    def _row_base_test_keys(
        row: dict,
        category: str,
        *,
        report_format: str = REPORT_FORMAT_WITH_LOGO,
    ) -> list[str]:
        row_category = normalize_category(category)
        if row_category == CATEGORY_WATER:
            return default_test_keys_for_category(CATEGORY_WATER)
        if row_category == CATEGORY_MICRO:
            return default_test_keys_for_category(CATEGORY_MICRO)
        if row_category == CATEGORY_FOOD:
            sample_name = _cell_text(row.get("Name of sample")).strip()
            ptype = normalize_package_type(_cell_text(row.get("Parameters")).strip())
            if sample_name and ptype:
                resolved = _cached_resolve_package_tests(
                    sample_name, ptype, row_category
                )
                if resolved:
                    fmt = report_format
                    if fmt == REPORT_FORMAT_WITH_LOGO:
                        return list(resolved.test_keys_with_logo)
                    if fmt == REPORT_FORMAT_WITHOUT_LOGO:
                        return list(resolved.test_keys_without_logo)
                    # Both — analyst works the union; logo lists stay separate on save
                    return list(resolved.test_keys)
            return []
        return []

    def _custom_options_for_row(row: dict, category: str) -> dict[str, str]:
        row_category = normalize_category(category)
        ptype = None
        ptype_key = ""
        if row_category == CATEGORY_FOOD:
            ptype = normalize_package_type(_cell_text(row.get("Parameters")).strip())
            ptype_key = ptype or ""
        formulas = _cached_custom_formulas_for_scope(row_category, ptype_key)
        return {custom_formula_select_label(f): f.test_key for f in formulas}

    def _merge_test_keys(base: list[str], custom: list[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for key in base + custom:
            if key and key not in seen:
                seen.add(key)
                merged.append(key)
        return merged

    def _custom_keys_for_row(row: dict, category: str) -> list[str]:
        try:
            sr_no = int(row.get("Sr. No") or 0)
        except (TypeError, ValueError):
            sr_no = 0
        options = _custom_options_for_row(row, category)
        selected_labels = st.session_state.get(f"custom_tests_sr_{sr_no}", [])
        return [options[label] for label in selected_labels if label in options]

    def _row_test_keys(
        row: dict,
        category: str,
        *,
        report_format: str = REPORT_FORMAT_WITH_LOGO,
    ) -> list[str]:
        base = _row_base_test_keys(row, category, report_format=report_format)
        custom = _custom_keys_for_row(row, category)
        return _merge_test_keys(base, custom)

    if request_prefill is not None:
        apply_request_prefill(request_prefill)
        prefill = request_prefill.customer

    p = _sync_customer_prefill(prefill)

    # Category + Parameters guidance (Food uses Parameters column for test type).
    render_section_title(
        "2. Sample category",
        "Choose Food, Water, Micro, or Cattle Feed / Fertilizer. **Food** rows "
        "pick a product name and **Parameters** (FSSAI, Basic Nutrition, or "
        "Detailed Nutrition) — tests load from the pre-saved package for that pair.",
    )
    cat_keys = list(SAMPLE_CATEGORIES.keys())
    cat_labels = [SAMPLE_CATEGORIES[k] for k in cat_keys]
    selected_cat_label = st.selectbox(
        "Sample category *",
        options=cat_labels,
        index=0,
        key="sample_category_select",
        help="Applies to all sample rows in this request.",
    )
    filter_category = cat_keys[cat_labels.index(selected_cat_label)]

    if filter_category == CATEGORY_WATER:
        st.info(
            "All **11 water protocol tests** are included automatically "
            "(no manual test selection required)."
        )
    elif filter_category == CATEGORY_MICRO:
        st.info(
            "All **6 microbiological tests** are included automatically "
            "(Total Plate Count, T.coliform, E. Coli, Salmonella, "
            "Staphylococcus aureus, Yeast and Mould)."
        )
    elif filter_category == CATEGORY_FOOD:
        st.info(
            "For each **Food** row: sample name (e.g. Jaggery, Masala) + **Parameters** "
            "(FSSAI, Basic Nutrition, or Detailed Nutrition). Tests come from the "
            "matching pre-saved package in **Test packages** — pick any Food catalog "
            "tests for each package; the same test name can appear in multiple packages."
        )
    else:
        st.info(
            f"No catalog tests are defined yet for **{selected_cat_label}**. "
            "Cattle Feed / Fertilizer formulas will appear when added."
        )

    contact_count = _render_contact_controls()

    from services.users import analyst_display_label, list_active_analysts

    analysts = list_active_analysts()
    analyst_options = [analyst_display_label(u) for u in analysts]
    label_to_id = {analyst_display_label(u): u.id for u in analysts}

    if not analyst_options:
        st.error("No active analyst users — create one in Admin before saving samples.")

    st.markdown(
        '<div class="sls-hint"><b>Sections 3–5 — Customer Test Request (printed form)</b> — '
        "Fields below match the printed CTR (LLP.docx).</div>",
        unsafe_allow_html=True,
    )

    # ----- Permanent customer block -----
    render_section_title(
        "3. Customer details (permanent database)",
        "These fields are upserted into PostgreSQL using GST number as the unique key.",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "Customer Details (Name / Company) *",
            key="f_customer_name",
        )
    with c2:
        st.text_area("Address *", height=100, key="f_address")

    render_section_title(
        "Contact persons",
        "Up to five contacts. Contact 1 name and email are required.",
    )
    for i in range(1, contact_count + 1):
        cc1, cc2 = st.columns(2)
        with cc1:
            st.text_input(
                f"Contact {i} — Name" + (" *" if i == 1 else ""),
                key=f"ctr_c{i}_name",
            )
        with cc2:
            st.text_input(
                f"Contact {i} — Email ID" + (" *" if i == 1 else ""),
                key=f"ctr_c{i}_email",
            )

    c3, c4 = st.columns(2)
    with c3:
        st.text_input(
            "Contact Number *",
            key="f_contact_number",
            help="Primary phone number for the customer.",
        )
    with c4:
        st.text_input(
            "GST Number *",
            key="f_gst_number",
            on_change=_on_gst_lookup,
            help=(
                "Permanent unique key. Enter a saved 15-character GST to auto-load "
                "name, address, and contacts — or use Section 1 to search by name."
            ),
        )
        gst_autoload_msg = st.session_state.get("customer_gst_autoload_msg")
        if gst_autoload_msg:
            st.info(gst_autoload_msg)
        st.caption(
            "Tip: type a full GSTIN here to load saved customer details, "
            "or search by name in Section 1."
        )

    # ----- Request-specific block (printed CTR header fields) -----
    render_section_title(
        "4. Test request details",
        "Date, sampling, service, and payment fields printed on the CTR form. "
        "Lab Code and sample table follow in the live-preview block below.",
    )

    r1, r2 = st.columns(2)
    with r1:
        if "f_request_date" not in st.session_state:
            st.session_state["f_request_date"] = None
        st.date_input(
            "Sample received date *",
            key="f_request_date",
            value=None,
            help="Date the sample was received (printed on CTR and used as Sample Received On).",
        )
    with r2:
        st.number_input(
            "Number of Samples",
            min_value=0,
            max_value=100,
            value=1,
            step=1,
            key="f_number_of_samples",
        )

    r4, r5 = st.columns(2)
    with r4:
        st.radio(
            "Sampling Done by Laboratory",
            options=["Not specified", "Yes", "No"],
            horizontal=True,
            key="f_sampling_choice",
        )
        st.radio(
            "Decision Rule required",
            options=["Not specified", "Yes", "No"],
            horizontal=True,
            key="f_decision_choice",
        )
    with r5:
        st.radio(
            "Service required",
            options=["", "Urgent", "Regular"],
            format_func=lambda x: "Not specified" if x == "" else x,
            horizontal=True,
            key="f_service_type",
        )
        st.selectbox(
            "Mode of report delivery",
            options=["", "Collect", "Courier", "Email/Whatsapp"],
            format_func=lambda x: "Not specified" if x == "" else x,
            key="f_delivery_mode",
        )

    st.text_input(
        "Storage Temperature of sample required",
        placeholder="e.g. Ambient / 2–8 °C / Frozen",
        key="f_storage_temperature",
    )
    st.text_area(
        "Specific test method / Specification to be followed",
        placeholder="e.g. FSSAI / IS method references",
        height=70,
        key="f_test_method_spec",
    )
    st.text_area(
        "Payment Details",
        placeholder="Advance amount, UTR, billing notes…",
        height=70,
        key="f_payment_details",
    )

    @st.fragment
    def _sample_workflow_fragment() -> None:
        """Lab code, sample table, and lab workflow — reruns live on edit."""
        st.text_input(
            "Lab Code *",
            key="f_lab_code",
            placeholder="e.g. SLS/26/306",
            help="Printed on the CTR form. Sample IDs in Section 6 are derived from this.",
        )

        render_section_title(
            "5. Sample table",
            "Matches the printed CTR form: Sr. No, Name of sample, Code/batch no., "
            "Sample qty., and Parameters. Code/batch no. is optional customer reference "
            "(may be empty or repeat across rows).",
        )

        default_rows = _default_sample_rows()
        if _SAMPLE_EDITOR_KEY not in st.session_state:
            st.session_state[_SAMPLE_EDITOR_KEY] = _normalize_ctr_df(
                pd.DataFrame(default_rows)
            )
        elif _SAMPLE_EDITOR_WIDGET_KEY not in st.session_state:
            # Migrate stored frame only before the widget has been mounted.
            st.session_state[_SAMPLE_EDITOR_KEY] = _migrate_sample_editor_df(
                st.session_state[_SAMPLE_EDITOR_KEY], filter_category
            )

        if edit_mode and request_prefill is not None:
            locked = [
                s.sample_code
                for s in request_prefill.samples
                if s.status != "pending"
            ]
            if locked:
                st.warning(
                    "Sample codes and analyst assignments locked (analyst started): "
                    + ", ".join(locked)
                )

        if filter_category == CATEGORY_FOOD:
            parameters_column = {
                "Parameters": st.column_config.SelectboxColumn(
                    "Parameters",
                    options=test_type_options,
                    help="FSSAI, Basic Nutrition, or Detailed Nutrition.",
                ),
            }
        elif filter_category == CATEGORY_WATER:
            parameters_column = {
                "Parameters": st.column_config.TextColumn(
                    "Parameters",
                    disabled=True,
                    help="Water: all 11 protocol tests are included automatically.",
                ),
            }
        elif filter_category == CATEGORY_MICRO:
            parameters_column = {
                "Parameters": st.column_config.TextColumn(
                    "Parameters",
                    disabled=True,
                    help="Micro: all 6 microbiological tests are included automatically.",
                ),
            }
        else:
            parameters_column = {
                "Parameters": st.column_config.TextColumn(
                    "Parameters",
                    help="Tests or specifications to be performed.",
                ),
            }

        # Do not write the return value back into the same session key used as
        # `data=` — that Streamlit pattern clears cell edits on Enter.
        sample_df = st.data_editor(
            st.session_state[_SAMPLE_EDITOR_KEY],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sr. No": st.column_config.NumberColumn("Sr. No", min_value=1, step=1),
                "Name of sample": st.column_config.TextColumn("Name of sample"),
                "Code/batch no.": st.column_config.TextColumn(
                    "Code/batch no.",
                    help="Customer batch/reference; optional; may repeat across rows.",
                ),
                "Sample qty.": st.column_config.TextColumn("Sample qty."),
                **parameters_column,
                "_sample_id": None,
                "_status": None,
            },
            key=_SAMPLE_EDITOR_WIDGET_KEY,
            disabled=not analyst_options,
        )
        sample_df = _normalize_ctr_df(sample_df)
        # Snapshot for Save outside this fragment (widget key is EditingState only).
        # If a full-app rerun remounts the editor blank, keep the last filled snapshot
        # so Save does not lose rows that the live preview already showed.
        prev_live = st.session_state.get(_SAMPLE_EDITOR_LIVE_KEY)
        if any(_sample_row_nonempty(r) for r in sample_df.to_dict(orient="records")):
            st.session_state[_SAMPLE_EDITOR_LIVE_KEY] = sample_df
        elif isinstance(prev_live, pd.DataFrame) and any(
            _sample_row_nonempty(r) for r in prev_live.to_dict(orient="records")
        ):
            sample_df = _normalize_ctr_df(prev_live)
        else:
            st.session_state[_SAMPLE_EDITOR_LIVE_KEY] = sample_df

        pinned_by_sr: dict[int, tuple[Optional[int], Optional[int]]] = {}
        if edit_mode and request_prefill is not None:
            for s in request_prefill.samples:
                if getattr(s, "package_id", None) is not None:
                    pinned_by_sr[s.sr_no] = (
                        s.package_id,
                        getattr(s, "package_version_no", None),
                    )

        for row in sample_df.to_dict(orient="records"):
            if normalize_category(filter_category) != CATEGORY_FOOD:
                continue
            sample_name = _cell_text(row.get("Name of sample")).strip()
            ptype = normalize_package_type(_cell_text(row.get("Parameters")).strip())
            try:
                sr_no = int(row.get("Sr. No") or 0)
            except (TypeError, ValueError):
                sr_no = 0
            if not sample_name and not ptype:
                continue
            if not sample_name:
                st.caption(f"Sr. {sr_no}: enter sample name to load tests.")
                continue
            if not ptype:
                st.caption(
                    f"Sr. {sr_no}: select Parameters (test type) for **{sample_name}**."
                )
                continue
            pinned = pinned_by_sr.get(sr_no, (None, None))
            custom_count = len(
                st.session_state.get(f"custom_tests_sr_{sr_no}", [])
            )
            _render_food_sample_package_block(
                sr_no=sr_no,
                sample_name=sample_name,
                ptype=ptype,
                filter_category=filter_category,
                pinned_package_id=pinned[0],
                pinned_version_no=pinned[1],
                custom_count=custom_count,
            )

        st.markdown(
            '<div class="sls-hint"><b>Section 6 — Lab workflow (not printed)</b> — '
            "Sample ID, analyst assignment, and report format are for internal "
            "lab handoff only.</div>",
            unsafe_allow_html=True,
        )
        render_section_title(
            "6. Lab workflow",
            "Sample ID is auto-generated from the Lab Code "
            "(e.g. SLS/26/306/01, /02 for each sample on the request). "
            "Enter protocol number, assign analyst, and report format below. "
            "With-logo and without-logo use **different** package test lists.",
        )

        st.text_area(
            "Internal notes (not printed on CTR)",
            height=70,
            key="f_sample_description",
            help="Optional reception notes; stored in the database but not on the printed form.",
        )

        analyst_select_options = [""] + analyst_options
        lab_code_preview = str(st.session_state.get("f_lab_code", "") or "")
        derived_codes = _sample_code_preview_map(lab_code_preview, sample_df)
        locked_code_by_sr: dict[int, str] = {}
        if edit_mode and request_prefill is not None:
            for s in request_prefill.samples:
                if s.status != "pending" and s.sample_code:
                    locked_code_by_sr[s.sr_no] = s.sample_code
        for row in sample_df.to_dict(orient="records"):
            if not _sample_row_nonempty(row):
                continue
            try:
                sr_no = int(row.get("Sr. No") or 0)
            except (TypeError, ValueError):
                continue
            status = str(row.get("_status") or "pending")
            locked = status != "pending"
            sample_label = _cell_text(row.get("Name of sample")).strip() or "(unnamed)"

            st.session_state.setdefault(
                f"workflow_report_format_{sr_no}",
                REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
            )

            st.markdown(f"**Sr. {sr_no}** — {sample_label}")
            if locked and sr_no in locked_code_by_sr:
                sample_id_label = locked_code_by_sr[sr_no]
            else:
                sample_id_label = derived_codes.get(sr_no, "") or "—"
            st.caption(f"Sample ID: **{sample_id_label}**")
            p_col, a_col, r_col = st.columns(3)
            with p_col:
                st.text_input(
                    "Protocol No *",
                    key=f"workflow_protocol_no_{sr_no}",
                    disabled=locked,
                    help="Printed on the analyst protocol document.",
                )
            with a_col:
                st.selectbox(
                    "Assigned analyst *",
                    options=analyst_select_options,
                    key=f"workflow_analyst_{sr_no}",
                    disabled=locked or not analyst_options,
                )
            with r_col:
                st.selectbox(
                    "Report format *",
                    options=report_format_options,
                    key=f"workflow_report_format_{sr_no}",
                    help=(
                        "A uses the package with-logo test set; "
                        "B uses the without-logo set; "
                        "Both stores both sets separately for the final report."
                    ),
                )

            options = _custom_options_for_row(row, filter_category)
            if options:
                st.multiselect(
                    f"Sr. {sr_no}: Additional formulas",
                    options=list(options.keys()),
                    key=f"custom_tests_sr_{sr_no}",
                    help="Optional custom tests from Admin for this category and test type.",
                )

            fmt_label = str(
                st.session_state.get(
                    f"workflow_report_format_{sr_no}",
                    REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
                )
            ).strip()
            fmt_key = LABEL_TO_REPORT_FORMAT.get(fmt_label, REPORT_FORMAT_WITH_LOGO)
            if normalize_category(filter_category) == CATEGORY_FOOD:
                sample_name = _cell_text(row.get("Name of sample")).strip()
                ptype = normalize_package_type(
                    _cell_text(row.get("Parameters")).strip()
                )
                if sample_name and ptype:
                    pkg_preview = _cached_resolve_package_tests(
                        sample_name, ptype, filter_category
                    )
                    if pkg_preview:
                        wl_keys = list(pkg_preview.test_keys_with_logo)
                        nwl_keys = list(pkg_preview.test_keys_without_logo)
                        if fmt_key == REPORT_FORMAT_WITH_LOGO:
                            names = ", ".join(get_test(k).name for k in wl_keys)
                            st.caption(
                                f"Tests added (with logo only): {names or '—'}"
                            )
                            if not wl_keys:
                                st.error(
                                    "Package has no with-logo tests for format A."
                                )
                        elif fmt_key == REPORT_FORMAT_WITHOUT_LOGO:
                            names = ", ".join(get_test(k).name for k in nwl_keys)
                            st.caption(
                                f"Tests added (without logo only): {names or '—'}"
                            )
                            if not nwl_keys:
                                st.error(
                                    "Package has no without-logo tests for format B. "
                                    "Add an NWL list in Test packages."
                                )
                        else:
                            wl = ", ".join(get_test(k).name for k in wl_keys)
                            nwl = ", ".join(get_test(k).name for k in nwl_keys)
                            st.caption(f"With-logo tests added: {wl or '—'}")
                            st.caption(f"Without-logo tests added: {nwl or '—'}")
                            if not wl_keys or not nwl_keys:
                                st.error(
                                    "Format Both needs **both** WL and NWL lists on the "
                                    "package (they must be configured separately)."
                                )

    _sample_workflow_fragment()

    if edit_mode:
        edit_reason = edit_reason_field(key="ctr_edit_reason")
    else:
        edit_reason = ""

    submitted = st.button(
        submit_label,
        use_container_width=True,
        type="primary",
        disabled=not analyst_options,
        key="ctr_save_button",
    )

    if not submitted:
        return None

    sample_df = _current_sample_editor_df()
    customer_name = str(st.session_state.get("f_customer_name", "") or "")
    address = str(st.session_state.get("f_address", "") or "")
    contact_number = str(st.session_state.get("f_contact_number", "") or "")
    gst_number = str(st.session_state.get("f_gst_number", "") or "")
    request_date = st.session_state.get("f_request_date")
    lab_code = str(st.session_state.get("f_lab_code", "") or "")
    number_of_samples = st.session_state.get("f_number_of_samples", 1)
    sampling_choice = str(st.session_state.get("f_sampling_choice", "Not specified") or "")
    decision_choice = str(st.session_state.get("f_decision_choice", "Not specified") or "")
    service_type = str(st.session_state.get("f_service_type", "") or "")
    delivery_mode = str(st.session_state.get("f_delivery_mode", "") or "")
    storage_temperature = str(st.session_state.get("f_storage_temperature", "") or "")
    test_method_spec = str(st.session_state.get("f_test_method_spec", "") or "")
    payment_details = str(st.session_state.get("f_payment_details", "") or "")
    sample_description = str(st.session_state.get("f_sample_description", "") or "")

    # Map Yes/No radios to Optional[bool]
    def yn(choice: str) -> Optional[bool]:
        if choice == "Yes":
            return True
        if choice == "No":
            return False
        return None

    samples: list[SampleRow] = []
    row_category = normalize_category(filter_category)

    for i, row in enumerate(sample_df.to_dict(orient="records"), start=1):
        sr = row.get("Sr. No") or i
        try:
            sr_no = int(sr)
        except (TypeError, ValueError):
            sr_no = i
        fmt_label = str(
            st.session_state.get(
                f"workflow_report_format_{sr_no}",
                REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
            )
            or ""
        ).strip()
        report_format = LABEL_TO_REPORT_FORMAT.get(fmt_label, REPORT_FORMAT_WITH_LOGO)
        row_keys = _row_test_keys(row, filter_category, report_format=report_format)
        params_text = _cell_text(row.get("Parameters")).strip()
        ptype = (
            normalize_package_type(params_text)
            if row_category == CATEGORY_FOOD
            else None
        )
        resolved = None
        sample_name = _cell_text(row.get("Name of sample")).strip()
        if row_category == CATEGORY_FOOD and sample_name and ptype:
            resolved = _cached_resolve_package_tests(
                sample_name,
                ptype,
                row_category,
            )
        tests_with_logo: list[str] = []
        tests_without_logo: list[str] = []
        if resolved:
            display_names = resolved.display_label
            if report_format == REPORT_FORMAT_WITH_LOGO:
                tests_with_logo = list(resolved.test_keys_with_logo)
            elif report_format == REPORT_FORMAT_WITHOUT_LOGO:
                tests_without_logo = list(resolved.test_keys_without_logo)
            else:
                tests_with_logo = list(resolved.test_keys_with_logo)
                tests_without_logo = list(resolved.test_keys_without_logo)
        elif row_category == CATEGORY_WATER:
            display_names = ", ".join(get_test(k).name for k in row_keys)
            if report_format == REPORT_FORMAT_WITH_LOGO:
                tests_with_logo = list(row_keys)
            elif report_format == REPORT_FORMAT_WITHOUT_LOGO:
                tests_without_logo = list(row_keys)
            else:
                tests_with_logo = list(row_keys)
                tests_without_logo = list(row_keys)
        elif row_category == CATEGORY_MICRO:
            display_names = ", ".join(get_test(k).name for k in row_keys)
            if report_format == REPORT_FORMAT_WITH_LOGO:
                tests_with_logo = list(row_keys)
            elif report_format == REPORT_FORMAT_WITHOUT_LOGO:
                tests_without_logo = list(row_keys)
            else:
                tests_with_logo = list(row_keys)
                tests_without_logo = list(row_keys)
        elif row_category == CATEGORY_FOOD:
            display_names = ", ".join(get_test(k).name for k in row_keys)
        else:
            display_names = params_text or ", ".join(
                get_test(k).name for k in row_keys
            )
        sample_id = row.get("_sample_id")
        if sample_id is not None and pd.isna(sample_id):
            sample_id = None
        elif sample_id is not None:
            try:
                sample_id = int(sample_id)
            except (TypeError, ValueError):
                sample_id = None
        status = _cell_text(row.get("_status")) or "pending"
        locked = status != "pending"
        analyst_label = str(
            st.session_state.get(f"workflow_analyst_{sr_no}", "") or ""
        ).strip()
        assigned_analyst_id = label_to_id.get(analyst_label)
        if locked and edit_mode and request_prefill is not None:
            old_sample = next(
                (s for s in request_prefill.samples if s.sr_no == sr_no),
                None,
            )
            protocol_no = (old_sample.protocol_no if old_sample else "") or ""
        else:
            protocol_no = str(
                st.session_state.get(f"workflow_protocol_no_{sr_no}", "") or ""
            ).strip()
        samples.append(
            SampleRow(
                id=sample_id,
                sr_no=sr_no,
                sample_name=_cell_text(row.get("Name of sample")),
                batch_code=_cell_text(row.get("Code/batch no.")),
                quantity=_cell_text(row.get("Sample qty.")),
                parameters=display_names,
                test_keys=list(row_keys),
                category=row_category,
                status=status,
                assigned_analyst_id=assigned_analyst_id,
                protocol_no=protocol_no,
                report_format=report_format,
                tests_with_logo=tests_with_logo,
                tests_without_logo=tests_without_logo,
                package_id=resolved.package_id if resolved else None,
                package_version_no=resolved.package_version_no if resolved else None,
                package_type=ptype if row_category == CATEGORY_FOOD else None,
            )
        )

    contacts = _read_contacts_from_session(contact_count)
    primary = contacts[0] if contacts else ContactPerson()
    customer = Customer(
        id=_resolved_customer_id(p, gst_number),
        customer_name=customer_name,
        address=address,
        contact_person=(primary.contact_name or "").strip(),
        contact_number=contact_number,
        email=(primary.email or "").strip(),
        gst_number=gst_number,
        contacts=contacts,
    )

    data = TestRequestData(
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
        request_id=request_prefill.request_id if request_prefill else None,
    )
    assign_derived_sample_codes(
        data,
        request_prefill if edit_mode else None,
    )
    return data, edit_reason
