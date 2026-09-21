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
from services.requests import (
    DELIVERY_MODE_OPTIONS,
    STORAGE_TEMPERATURE_OPTIONS,
    STORAGE_TEMPERATURE_OTHER,
    SampleRow,
    TestRequestData,
    assign_derived_sample_codes,
    format_delivery_modes,
    parse_delivery_modes,
    storage_temperature_for_save,
    storage_temperature_select_value,
    sync_verify_sample_code,
)
from services.versions import validate_edit_reason


# Path to the CSS file next to this module
STYLES_PATH = Path(__file__).resolve().parent / "styles.css"


def _bool_to_yn_choice(value: Optional[bool]) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not specified"


def _yn_choice_to_bool(choice: str) -> Optional[bool]:
    if choice == "Yes":
        return True
    if choice == "No":
        return False
    return None


@st.cache_data(ttl=60)
def _cached_resolve_package_for_product(
    sample_name: str,
    package_type_key: str,
    category: str,
):
    """Cache product-name test package resolution across fragment reruns."""
    from services.test_packages import (
        normalize_package_type,
        resolve_package_for_product,
        resolve_package_tests,
    )

    ptype = normalize_package_type(package_type_key) if package_type_key else None
    if ptype:
        return resolve_package_tests(sample_name, ptype, category=category)
    return resolve_package_for_product(sample_name, category=category)


def _food_package_type_key_for_row(sample_name: str, sr_no: int, category: str) -> str:
    """Package type key from ambiguous picker or empty for single-package products."""
    from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category
    from services.test_packages import (
        describe_sample_package_for_product,
        parameters_label_to_package_type,
    )

    if normalize_category(category) != CATEGORY_FOOD or not (sample_name or "").strip():
        return ""
    desc = describe_sample_package_for_product(sample_name, category=category)
    if desc.get("status") == "ambiguous":
        label = str(st.session_state.get(f"test_package_type_{sr_no}", "") or "")
        return parameters_label_to_package_type(label) or ""
    return ""


def _food_resolved_for_row(row: dict, category: str):
    """Resolved test package for a Food sample table row."""
    from services.test_packages import get_package, package_to_resolved

    sample_name = _cell_text(row.get("Name of sample")).strip()
    if not sample_name:
        return None
    try:
        sr_no = int(row.get("Sr. No") or 0)
    except (TypeError, ValueError):
        sr_no = 0
    pinned = st.session_state.get("intake_pinned_package_id")
    if pinned and sr_no == 1:
        pkg = get_package(int(pinned))
        if (
            pkg
            and pkg.sample_product_name.strip().lower()
            == sample_name.strip().lower()
        ):
            return package_to_resolved(pkg)
    ptype_key = _food_package_type_key_for_row(sample_name, sr_no, category)
    return _cached_resolve_package_for_product(sample_name, ptype_key, category)


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


def _food_parameters_label_for_row(sr_no: int, row: dict) -> str:
    """Parameters (CTR column) for a Food row — stored per-row outside the table."""
    from services.test_packages import CTR_PARAMETER_OPTIONS

    key = f"food_parameters_{sr_no}"
    if key in st.session_state:
        return str(st.session_state.get(key) or "").strip()
    existing = _cell_text(row.get("Parameters")).strip()
    if existing:
        return existing
    return CTR_PARAMETER_OPTIONS[0] if CTR_PARAMETER_OPTIONS else ""


def _render_food_parameters_for_row(
    *,
    sr_no: int,
    row: dict,
    locked: bool,
) -> str:
    """Per-row Parameters select (printed on CTR). Returns selected label."""
    from services.test_packages import CTR_PARAMETER_OPTIONS, CTR_PARAMETER_OTHER

    key = f"food_parameters_{sr_no}"
    if key not in st.session_state:
        existing = _cell_text(row.get("Parameters")).strip()
        st.session_state[key] = existing or CTR_PARAMETER_OPTIONS[0]
    label = st.selectbox(
        "Parameters (printed on CTR) *",
        options=CTR_PARAMETER_OPTIONS,
        key=key,
        disabled=locked,
        help="FSSAI, Basic Nutrition, Detailed Nutrition, or Other — printed in the CTR Parameters column.",
    )
    if label == CTR_PARAMETER_OTHER:
        st.text_input(
            "Parameters text for CTR *",
            key=f"parameters_other_{sr_no}",
            disabled=locked,
            help="Custom text printed in the Parameters column when Other is selected.",
        )
    return str(label or "").strip()


def _render_food_sample_package_block(
    *,
    sr_no: int,
    sample_name: str,
    parameters_label: str,
    filter_category: str,
    custom_count: int = 0,
    actor=None,
) -> Optional[object]:
    """Show package status and available tests for a Food sample row."""
    from services.protocols.test_catalog import CATEGORY_FOOD, get_test, normalize_category
    from services.test_packages import (
        create_package_from_source,
        describe_sample_package_for_product,
        get_package,
    )

    if normalize_category(filter_category) != CATEGORY_FOOD:
        return None

    _ = parameters_label  # CTR Parameters label is chosen per-row above this block.

    desc = describe_sample_package_for_product(
        sample_name,
        category=filter_category,
    )
    status = desc["status"]
    extra = f" + {custom_count} custom" if custom_count else ""

    if status == "duplicate":
        dup_ids = desc.get("duplicate_package_ids") or []
        id_list = ", ".join(f"#{pid}" for pid in dup_ids)
        st.error(
            f"**Duplicate packages** — multiple active packages exist for "
            f"**{sample_name}** ({id_list}). Deactivate extras under **Test packages**."
        )
    elif status == "ambiguous":
        options = [""] + list(desc.get("ambiguous_types") or [])
        st.selectbox(
            "Test package *",
            options=options,
            format_func=lambda x: "Select package type…" if x == "" else x,
            key=f"test_package_type_{sr_no}",
            help="Multiple packages exist for this product — choose which tests to load.",
        )

    resolved = _food_resolved_for_row(
        {"Sr. No": sr_no, "Name of sample": sample_name},
        filter_category,
    )

    if status == "defined":
        wl_keys = desc.get("test_keys_with_logo", [])
        nwl_keys = desc.get("test_keys_without_logo", [])
        wl_names = ", ".join(get_test(k).name for k in wl_keys)
        nwl_names = ", ".join(get_test(k).name for k in nwl_keys)
        st.success(f"**Defined** — **{sample_name}**{extra}")
        if wl_keys:
            st.caption(f"With logo: {len(wl_keys)} tests — {wl_names or '—'}")
        if nwl_keys:
            st.caption(f"Without logo: {len(nwl_keys)} tests — {nwl_names or '—'}")
    elif status == "inactive":
        st.warning(
            f"**Inactive** — a package for **{sample_name}** exists "
            "but is deactivated. Activate it under **Test packages** before saving."
        )
    elif status == "ambiguous":
        if resolved:
            test_keys = list(resolved.test_keys)
            test_names = ", ".join(get_test(k).name for k in test_keys)
            st.success(
                f"**Defined** — **{sample_name}** "
                f"({len(test_keys)} tests available{extra}): {test_names or '—'}"
            )
        else:
            st.warning(
                f"**Multiple packages** — select a test package for **{sample_name}** above."
            )
    else:
        similar = list(desc.get("similar_packages") or [])
        if similar:
            reason_labels = {
                "prefix": "name prefix",
                "contains": "name contains",
                "word": "shared word",
            }
            lines = []
            for item in similar:
                pname = item.get("sample_product_name", "")
                count = int(item.get("test_count") or 0)
                reason = reason_labels.get(
                    str(item.get("match_reason") or ""),
                    str(item.get("match_reason") or "similar"),
                )
                lines.append(f"**{pname}** ({count} tests, {reason})")
            st.info(
                f"No active package for **{sample_name}**. "
                f"Similar registered product{'s' if len(similar) != 1 else ''}: "
                + "; ".join(lines)
            )
            if len(similar) == 1:
                source_id = int(similar[0]["package_id"])
                source_name = str(similar[0].get("sample_product_name") or "")
            else:
                options = {
                    f"{item['sample_product_name']} ({item.get('test_count', 0)} tests)": int(
                        item["package_id"]
                    )
                    for item in similar
                }
                pick = st.selectbox(
                    "Copy tests from similar product",
                    options=list(options.keys()),
                    key=f"pkg_similar_pick_{sr_no}",
                )
                source_id = options[pick]
                source_name = pick.split(" (", 1)[0]
            if st.button(
                f"Copy tests from {source_name} and define package",
                key=f"pkg_copy_similar_{sr_no}",
            ):
                try:
                    create_package_from_source(
                        sample_name,
                        source_id,
                        category=filter_category,
                        actor=actor,
                    )
                    _cached_resolve_package_for_product.clear()
                    st.success(
                        f"Created test package for **{sample_name}** "
                        f"from **{source_name}**."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            st.caption("Or create manually under **Test packages**.")
        else:
            st.warning(
                f"**Not defined** — no active test package for **{sample_name}**. "
                "Create it under **Test packages**."
            )

    manage_id = desc.get("package_id")
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
                "Manage package in Sample registration",
                key=f"pkg_manage_{sr_no}",
            ):
                persist_sample_editor_state()
                st.session_state["reception_tab"] = RECEPTION_TAB_REGISTRATION
                st.session_state["_reception_tab_last"] = RECEPTION_TAB_REGISTRATION
                st.session_state["_reception_mode_last"] = RECEPTION_TAB_REGISTRATION
                st.session_state["pkg_edit_select"] = select_label
                st.rerun()

    return resolved


def _intake_test_label_options(test_keys: list[str]) -> tuple[list[str], dict[str, str]]:
    """Map catalog keys to multiselect labels for intake."""
    from services.protocols.test_catalog import get_test

    labels: list[str] = []
    label_to_key: dict[str, str] = {}
    for key in test_keys:
        label = get_test(key).name
        labels.append(label)
        label_to_key[label] = key
    return labels, label_to_key


def _labels_to_test_keys(labels: list[str], label_to_key: dict[str, str]) -> list[str]:
    return [label_to_key[label] for label in labels if label in label_to_key]


def _test_keys_to_labels(keys: list[str], label_to_key: dict[str, str]) -> list[str]:
    key_to_label = {v: k for k, v in label_to_key.items()}
    return [key_to_label[k] for k in keys if k in key_to_label]


def _render_food_intake_test_selection(
    *,
    sr_no: int,
    resolved: object,
    locked: bool,
    report_format_options: list[str],
) -> None:
    """Report format + with-logo / without-logo test multiselects from package pool."""
    from services.samples import (
        LABEL_TO_REPORT_FORMAT,
        REPORT_FORMAT_BOTH,
        REPORT_FORMAT_LABELS,
        REPORT_FORMAT_WITHOUT_LOGO,
        REPORT_FORMAT_WITH_LOGO,
    )

    st.session_state.setdefault(
        f"workflow_report_format_{sr_no}",
        REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
    )
    fmt_label = st.selectbox(
        "Report format *",
        options=report_format_options,
        key=f"workflow_report_format_{sr_no}",
        disabled=locked,
        help=(
            "A uses the with-logo test selection; B uses the without-logo selection; "
            "Both stores both lists separately for the final report."
        ),
    )
    fmt_key = LABEL_TO_REPORT_FORMAT.get(fmt_label, REPORT_FORMAT_WITH_LOGO)

    wl_labels, wl_map = _intake_test_label_options(list(resolved.test_keys_with_logo))
    nwl_labels, nwl_map = _intake_test_label_options(
        list(resolved.test_keys_without_logo)
    )
    wl_key = f"intake_wl_labels_{sr_no}"
    nwl_key = f"intake_nwl_labels_{sr_no}"
    if wl_key not in st.session_state and wl_labels:
        st.session_state[wl_key] = list(wl_labels)
    if nwl_key not in st.session_state and nwl_labels:
        st.session_state[nwl_key] = list(nwl_labels)
    st.session_state.setdefault(wl_key, [])
    st.session_state.setdefault(nwl_key, [])

    if fmt_key in (REPORT_FORMAT_WITH_LOGO, REPORT_FORMAT_BOTH):
        st.multiselect(
            "Tests with logo *",
            options=wl_labels,
            key=wl_key,
            disabled=locked,
            help="Select tests from the package for reports with lab letterhead.",
        )
    if fmt_key in (REPORT_FORMAT_WITHOUT_LOGO, REPORT_FORMAT_BOTH):
        st.multiselect(
            "Tests without logo *",
            options=nwl_labels,
            key=nwl_key,
            disabled=locked,
            help="Select tests from the package for reports without letterhead.",
        )

    wl_keys = _labels_to_test_keys(st.session_state.get(wl_key, []), wl_map)
    nwl_keys = _labels_to_test_keys(st.session_state.get(nwl_key, []), nwl_map)
    st.session_state[f"intake_wl_keys_{sr_no}"] = wl_keys
    st.session_state[f"intake_nwl_keys_{sr_no}"] = nwl_keys

    overlap = set(wl_keys) & set(nwl_keys)
    if overlap:
        from services.protocols.test_catalog import get_test

        names = ", ".join(get_test(k).name for k in overlap)
        st.error(f"The same test cannot be in both lists: {names}")


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


RECEPTION_TAB_REGISTRATION = "Sample registration"
RECEPTION_TAB_CUSTOMERS = "Customers"
RECEPTION_TAB_NEW = "New sample registration"
RECEPTION_TAB_EDIT = "Edit existing request"
RECEPTION_TABS = (
    RECEPTION_TAB_REGISTRATION,
    RECEPTION_TAB_CUSTOMERS,
    RECEPTION_TAB_NEW,
    RECEPTION_TAB_EDIT,
)

# Backward-compatible aliases (tests / legacy session keys)
RECEPTION_MODE_PACKAGES = RECEPTION_TAB_REGISTRATION
RECEPTION_MODE_NEW = RECEPTION_TAB_NEW
RECEPTION_MODE_EDIT = RECEPTION_TAB_EDIT


def should_clear_ctr_form_on_mode_change(old_mode: str, new_mode: str) -> bool:
    """Clear intake draft only when switching between new registration and edit."""
    intake_modes = {RECEPTION_TAB_NEW, RECEPTION_TAB_EDIT}
    return (
        old_mode in intake_modes
        and new_mode in intake_modes
        and old_mode != new_mode
    )


def mark_reception_tab(tab_name: str) -> None:
    """Track active Reception tab; persist/clear CTR draft on tab switches."""
    new_mode = str(tab_name or RECEPTION_TAB_NEW)
    old_mode = str(
        st.session_state.get("_reception_tab_last")
        or st.session_state.get("_reception_mode_last")
        or RECEPTION_TAB_NEW
    )
    if old_mode == RECEPTION_TAB_NEW and new_mode != RECEPTION_TAB_NEW:
        persist_sample_editor_state()
    if should_clear_ctr_form_on_mode_change(old_mode, new_mode):
        clear_ctr_form_state()
    st.session_state["_reception_tab_last"] = new_mode
    st.session_state["_reception_mode_last"] = new_mode
    st.session_state["reception_tab"] = new_mode


def handle_reception_mode_change() -> None:
    """Legacy radio on_change — delegates to mark_reception_tab."""
    mark_reception_tab(
        str(st.session_state.get("reception_mode") or RECEPTION_TAB_NEW)
    )


def handle_reception_tab_change() -> None:
    """Tab/select on_change — delegates to mark_reception_tab."""
    mark_reception_tab(str(st.session_state.get("reception_tab") or RECEPTION_TAB_NEW))


def food_intake_packages_ready(
    rows: list[dict],
    category: str,
    *,
    session: Optional[dict] = None,
) -> tuple[bool, list[str]]:
    """
    True when every named Food sample row has an active, resolved test package.

    Used to gate customer sections on New request until packages exist.
    """
    from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category
    from services.test_packages import (
        describe_sample_package_for_product,
        parameters_label_to_package_type,
    )

    if normalize_category(category) != CATEGORY_FOOD:
        return True, []

    state = session if session is not None else st.session_state
    blocked: list[str] = []
    has_named_row = False

    for row in rows:
        if not _sample_row_nonempty(row):
            continue
        sample_name = _cell_text(row.get("Name of sample")).strip()
        if not sample_name:
            continue
        has_named_row = True
        try:
            sr_no = int(row.get("Sr. No") or 0)
        except (TypeError, ValueError):
            sr_no = 0

        desc = describe_sample_package_for_product(sample_name, category=category)
        status = desc.get("status")

        if status == "defined":
            continue
        if status in ("ambiguous", "duplicate"):
            if status == "duplicate":
                blocked.append(
                    f"{sample_name} (duplicate active packages — deactivate extras under Test packages)"
                )
                continue
            label = str(state.get(f"test_package_type_{sr_no}", "") or "").strip()
            if label and parameters_label_to_package_type(label):
                continue
            blocked.append(f"{sample_name} (select test package type)")
            continue
        if status == "inactive":
            blocked.append(f"{sample_name} (package inactive — activate under Test packages)")
            continue
        blocked.append(f"{sample_name} (no package defined — create under Test packages)")

    if not has_named_row:
        return False, ["Enter at least one sample product name in the table below"]

    return len(blocked) == 0, blocked


def ctr_section_numbers(
    *,
    sample_first: bool,
    include_customer_picker: bool,
    filter_category: str,
    food_package_first: bool = False,
) -> dict[str, int]:
    """Sequential section numbers matching on-screen display order in collect_form."""
    from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category

    include_test_selection = normalize_category(filter_category) == CATEGORY_FOOD
    _ = sample_first  # legacy parameter

    order = ["category"]
    if food_package_first and include_test_selection:
        order.extend(["sample_table", "test_selection"])
        if include_customer_picker:
            order.append("customer_lookup")
        order.extend(
            [
                "customer_details",
                "contact_persons",
                "request_details",
                "lab_code",
            ]
        )
    else:
        if include_customer_picker:
            order.append("customer_lookup")
        order.extend(
            [
                "customer_details",
                "contact_persons",
                "request_details",
                "lab_code",
                "sample_table",
            ]
        )
        if include_test_selection:
            order.append("test_selection")
    order.append("lab_workflow")

    return {name: index + 1 for index, name in enumerate(order)}


def customer_picker_keys(key_prefix: str = "ctr_") -> dict[str, str]:
    """Session/widget key names for a namespaced customer picker instance."""
    prefix = (key_prefix or "ctr_").strip()
    return {
        "search_q": f"{prefix}customer_search_q",
        "select": f"{prefix}customer_select",
        "prev_q": f"{prefix}_customer_search_prev_q",
        "results": f"{prefix}customer_search_results",
        "error": f"{prefix}customer_search_error",
    }


def _refresh_customer_search(key_prefix: str = "ctr_") -> None:
    """Run customer master search from the customer lookup box."""
    keys = customer_picker_keys(key_prefix)
    query = str(st.session_state.get(keys["search_q"]) or "")
    try:
        st.session_state[keys["results"]] = search_customers(query)
        st.session_state.pop(keys["error"], None)
    except Exception as exc:  # noqa: BLE001
        st.session_state[keys["error"]] = str(exc)
        st.session_state[keys["results"]] = []


def apply_customer_to_session(
    customer: Customer,
    *,
    autoload_msg: str | None = None,
) -> None:
    """Write permanent customer fields into CTR / customer-master widget keys."""
    _push_customer_to_session(customer, autoload_msg=autoload_msg)


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
    """Auto-load permanent customer when a full GSTIN is entered in customer details."""
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


def customer_picker(
    *,
    lookup_no: int,
    customer_details_no: int,
    key_prefix: str = "ctr_",
) -> Optional[Customer]:
    """
    Search / select an existing permanent customer.

    Returns
    -------
    Customer or None
        Selected customer to autofill the form, or None if user chose "New".
    """
    keys = customer_picker_keys(key_prefix)

    def _on_search_change() -> None:
        _refresh_customer_search(key_prefix)

    render_section_title(
        f"{lookup_no}. Existing customer lookup",
        "Search by GST or customer name — results update as you type. "
        f"Or enter a full 15-character GST in Section {customer_details_no} "
        "to auto-load saved details.",
    )

    query = st.text_input(
        "Search GST / customer name",
        placeholder="e.g. 27AAAAA0000A1Z5 or Acme Foods",
        key=keys["search_q"],
        on_change=_on_search_change,
    )

    prev_q = st.session_state.get(keys["prev_q"])
    if prev_q != query or keys["results"] not in st.session_state:
        st.session_state[keys["prev_q"]] = query
        _refresh_customer_search(key_prefix)

    search_error = st.session_state.get(keys["error"])
    if search_error:
        st.warning(f"Could not search customers: {search_error}")

    results: list[Customer] = st.session_state.get(keys["results"], [])
    if results:
        st.caption(
            f"{len(results)} customer(s) shown. Empty search lists recent customers."
        )

    options = ["— New customer —"] + [
        f"{c.customer_name}  |  GST: {c.gst_number}  (#{c.id})" for c in results
    ]
    choice = st.selectbox("Select customer to autofill", options, key=keys["select"])

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


def read_customer_from_session(
    *,
    contact_count: int | None = None,
    prefill: Customer | None = None,
) -> Customer:
    """Build a Customer from intake / customer-master widget session keys."""
    count = contact_count
    if count is None:
        count = int(st.session_state.get("ctr_contact_count", 1))
    count = max(1, min(int(count), MAX_CONTACTS))
    contacts = _read_contacts_from_session(count)
    primary = contacts[0] if contacts else ContactPerson()
    gst_number = str(st.session_state.get("f_gst_number", "") or "")
    p = prefill or Customer(
        customer_name="",
        address="",
        contact_person="",
        contact_number="",
        email="",
        gst_number="",
    )
    return Customer(
        id=_resolved_customer_id(p, gst_number),
        customer_name=str(st.session_state.get("f_customer_name", "") or ""),
        address=str(st.session_state.get("f_address", "") or ""),
        contact_person=(primary.contact_name or "").strip(),
        contact_number=str(st.session_state.get("f_contact_number", "") or ""),
        email=(primary.email or "").strip(),
        gst_number=gst_number,
        contacts=contacts,
    )


def render_customer_details_form(
    *,
    section_no: int = 1,
    show_gst_autoload: bool = True,
) -> int:
    """
    Editable customer + contact fields (shared by CTR intake and customer master).

    Returns active contact-person count.
    """
    render_section_title(
        f"{section_no}. Customer details",
        "Saved to PostgreSQL. GST is optional; when provided it is the unique lookup key.",
    )
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "Customer Details (Name / Company) *",
            key="f_customer_name",
        )
    with c2:
        st.text_area("Address *", height=100, key="f_address")

    contact_count = _render_contact_controls()

    render_section_title(
        f"{section_no + 1}. Contact persons",
        "Up to five contacts. Contact 1 name is required.",
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
                f"Contact {i} — Email ID"
                + (" (optional)" if i == 1 else ""),
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
            "GST Number (optional)",
            key="f_gst_number",
            on_change=_on_gst_lookup if show_gst_autoload else None,
            help=(
                "Optional. Enter a saved 15-character GSTIN to auto-load "
                "name, address, and contacts."
            ),
        )
        if show_gst_autoload:
            gst_autoload_msg = st.session_state.get("customer_gst_autoload_msg")
            if gst_autoload_msg:
                st.info(gst_autoload_msg)
    return contact_count


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
    "Category",
    "Name of sample",
    "Code/batch no.",
    "Sample qty.",
    "Parameters",
    "_sample_id",
    "_status",
)
_CTR_TEXT_COLUMNS = (
    "Category",
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


def _default_sample_rows(count: int = 1, *, default_category: str = "Food") -> list[dict]:
    return [
        {
            "Sr. No": i,
            "Category": default_category,
            "Name of sample": "",
            "Code/batch no.": "",
            "Sample qty.": "",
            "Parameters": "",
            "_sample_id": None,
            "_status": "pending",
        }
        for i in range(1, count + 1)
    ]


def _category_key_from_row(row: dict, cat_key_by_label: dict[str, str]) -> str:
    from services.protocols.test_catalog import CATEGORY_FOOD, normalize_category

    label = _cell_text(row.get("Category")).strip()
    if label in cat_key_by_label:
        return normalize_category(cat_key_by_label[label])
    if label:
        return normalize_category(label.replace(" ", "_"))
    return CATEGORY_FOOD


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


def _apply_data_editor_state(base_df: pd.DataFrame, editing_state: dict) -> pd.DataFrame:
    """Merge Streamlit data_editor EditingState into a DataFrame."""
    out = _normalize_ctr_df(base_df).copy()
    edited = editing_state.get("edited_rows") or {}
    for idx_str, changes in edited.items():
        try:
            idx = int(idx_str)
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(out):
            continue
        for col, val in (changes or {}).items():
            if col in out.columns:
                out.at[out.index[idx], col] = val

    for new_row in editing_state.get("added_rows") or []:
        if not isinstance(new_row, dict):
            continue
        row_dict = {col: new_row.get(col, "") for col in _CTR_TABLE_COLUMNS}
        if not row_dict.get("_status"):
            row_dict["_status"] = "pending"
        out = pd.concat([out, pd.DataFrame([row_dict])], ignore_index=True)

    deleted = editing_state.get("deleted_rows") or []
    if deleted:
        keep = [i for i in range(len(out)) if i not in deleted]
        out = out.iloc[keep].reset_index(drop=True)

    return _normalize_ctr_df(out)


def persist_sample_editor_state() -> None:
    """Snapshot sample table edits before leaving New request."""
    merged = _sample_editor_df_for_render()
    st.session_state[_SAMPLE_EDITOR_KEY] = merged
    st.session_state[_SAMPLE_EDITOR_LIVE_KEY] = merged


def apply_pinned_package_to_intake(pkg) -> None:
    """Pre-fill row 1 of the sample table from a selected test package."""
    from services.test_packages import PACKAGE_TYPES

    st.session_state["intake_pinned_package_id"] = int(pkg.id)
    param_label = PACKAGE_TYPES.get(pkg.package_type, pkg.package_type_label)
    df = pd.DataFrame(
        [
            {
                "Sr. No": 1,
                "Name of sample": pkg.sample_product_name,
                "Code/batch no.": "",
                "Sample qty.": "",
                "Parameters": param_label,
                "_sample_id": None,
                "_status": "pending",
            }
        ]
    )
    _reset_sample_editor(df)
    st.session_state["food_parameters_1"] = param_label
    st.session_state["test_package_type_1"] = pkg.package_type_label


def _sample_editor_df_for_render() -> pd.DataFrame:
    """Merge pending data_editor edits before passing data= to the widget."""
    base = _current_sample_editor_df()
    widget = st.session_state.get(_SAMPLE_EDITOR_WIDGET_KEY)
    if isinstance(widget, dict):
        return _apply_data_editor_state(base, widget)
    return base


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
    if _cell_text(row.get("Name of sample")).strip():
        return True
    return any(
        _cell_text(row.get(col)).strip()
        for col in ("Sample qty.", "Parameters")
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

    if all(c in df.columns for c in _CTR_TABLE_COLUMNS):
        return _normalize_ctr_df(df)

    if "Category" not in df.columns:
        from services.sample_categories import all_sample_categories

        default_label = all_sample_categories().get(
            normalize_category(category), "Food"
        )
        df = df.copy()
        df["Category"] = default_label

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
        if "Micro analyst" in df.columns:
            st.session_state.setdefault(
                f"workflow_micro_analyst_{sr_no}",
                _cell_text(row.get("Micro analyst")),
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
        st.session_state["f_delivery_mode"] = parse_delivery_modes(
            request.delivery_mode
        )
        storage_select = storage_temperature_select_value(request.storage_temperature)
        st.session_state["f_storage_temperature"] = storage_select
        if storage_select == STORAGE_TEMPERATURE_OTHER:
            st.session_state["f_storage_temperature_other"] = (
                request.storage_temperature or ""
            ).strip()
        st.session_state["f_test_method_spec"] = request.test_method_spec or ""
        st.session_state["f_payment_details"] = request.payment_details or ""
        st.session_state["f_sample_description"] = request.sample_description or ""

        from services.protocols.test_catalog import (
            CATEGORY_FOOD,
            CATEGORY_MICRO,
            CATEGORY_WATER,
            TEST_CATALOG,
            normalize_category,
        )
        from services.sample_categories import all_sample_categories
        from services.test_packages import (
            CTR_PARAMETER_OTHER,
            ctr_parameters_select_value,
            normalize_package_type,
            package_type_label,
            resolve_package_for_product,
            resolve_package_tests,
        )
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
                params_val = ctr_parameters_select_value(
                    s.parameters, s.package_type
                )
                if params_val == CTR_PARAMETER_OTHER:
                    custom = (s.parameters or "").strip()
                    st.session_state[f"parameters_other_{s.sr_no}"] = custom
                st.session_state[f"food_parameters_{s.sr_no}"] = params_val
                keys = list(s.test_keys or [])
                if not keys:
                    keys = list(s.tests_with_logo or []) + list(
                        s.tests_without_logo or []
                    )
            elif cat in (CATEGORY_WATER, CATEGORY_MICRO):
                params_val = ""
            else:
                params_val = s.parameters or ""
            cats = all_sample_categories()
            cat_label = cats.get(cat, list(cats.values())[0])
            rows.append(
                {
                    "Sr. No": s.sr_no,
                    "Category": cat_label,
                    "Name of sample": s.sample_name or "",
                    "Code/batch no.": s.batch_code or "",
                    "Sample qty.": s.quantity or "",
                    "Parameters": params_val,
                    "_sample_id": s.id,
                    "_status": s.status,
                }
            )
            st.session_state.setdefault(
                f"f_storage_temperature_{s.sr_no}",
                storage_temperature_select_value(
                    getattr(s, "storage_temperature", None) or request.storage_temperature
                ),
            )
            if (
                st.session_state.get(f"f_storage_temperature_{s.sr_no}")
                == STORAGE_TEMPERATURE_OTHER
            ):
                st.session_state.setdefault(
                    f"f_storage_temperature_other_{s.sr_no}",
                    getattr(s, "storage_temperature", None) or request.storage_temperature or "",
                )
            samp = getattr(s, "sampling_by_lab", None)
            if samp is None:
                samp = request.sampling_by_lab
            st.session_state.setdefault(
                f"f_sampling_choice_{s.sr_no}", _bool_to_yn_choice(samp)
            )
            dec = getattr(s, "decision_rule", None)
            if dec is None:
                dec = request.decision_rule
            st.session_state.setdefault(
                f"f_decision_choice_{s.sr_no}", _bool_to_yn_choice(dec)
            )
            st.session_state.setdefault(
                f"f_service_type_{s.sr_no}",
                getattr(s, "service_type", None) or request.service_type or "",
            )
            st.session_state.setdefault(
                f"f_delivery_mode_{s.sr_no}",
                parse_delivery_modes(
                    getattr(s, "delivery_mode", None) or request.delivery_mode or ""
                ),
            )
            st.session_state.setdefault(
                f"f_test_method_spec_{s.sr_no}",
                getattr(s, "test_method_spec", None) or request.test_method_spec or "",
            )
            st.session_state[f"workflow_analyst_{s.sr_no}"] = id_to_label.get(
                s.assigned_analyst_id, ""
            )
            st.session_state[f"workflow_micro_analyst_{s.sr_no}"] = id_to_label.get(
                getattr(s, "assigned_micro_analyst_id", None), ""
            )
            st.session_state[f"workflow_protocol_no_{s.sr_no}"] = (
                getattr(s, "protocol_no", "") or ""
            )
            st.session_state[f"workflow_report_format_{s.sr_no}"] = report_format_label(
                s.report_format
            )
            if cat == CATEGORY_FOOD:
                ptype = normalize_package_type(s.package_type)
                if ptype:
                    st.session_state[f"test_package_type_{s.sr_no}"] = package_type_label(
                        ptype
                    )
                resolved = None
                if (s.sample_name or "").strip():
                    if ptype:
                        resolved = resolve_package_tests(
                            s.sample_name or "", ptype, category=cat
                        )
                    else:
                        resolved = resolve_package_for_product(
                            s.sample_name or "", category=cat
                        )
                pool_wl = list(resolved.test_keys_with_logo) if resolved else []
                pool_nwl = list(resolved.test_keys_without_logo) if resolved else []
                _, wl_map = _intake_test_label_options(pool_wl)
                _, nwl_map = _intake_test_label_options(pool_nwl)
                st.session_state[f"intake_wl_labels_{s.sr_no}"] = _test_keys_to_labels(
                    list(s.tests_with_logo or []), wl_map
                )
                st.session_state[f"intake_nwl_labels_{s.sr_no}"] = _test_keys_to_labels(
                    list(s.tests_without_logo or []), nwl_map
                )
                st.session_state[f"intake_wl_keys_{s.sr_no}"] = list(
                    s.tests_with_logo or []
                )
                st.session_state[f"intake_nwl_keys_{s.sr_no}"] = list(
                    s.tests_without_logo or []
                )
            st.session_state[f"verify_review_date_{s.sr_no}"] = (
                s.verify_review_date or request.request_date
            )
            st.session_state[f"verify_lab_code_{s.sr_no}"] = (
                s.verify_lab_code or request.lab_code or ""
            )
            st.session_state[f"verify_sample_code_{s.sr_no}"] = (
                getattr(s, "verify_sample_code", None) or s.sample_code or ""
            )
            st.session_state[f"verify_sample_condition_{s.sr_no}"] = (
                s.verify_sample_condition or ""
            )
            st.session_state[f"verify_qty_checked_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_qty_checked
            )
            st.session_state[f"verify_chemical_available_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_chemical_available
            )
            st.session_state[f"verify_methods_available_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_methods_available
            )
            st.session_state[f"verify_methods_informed_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_methods_informed
            )
            st.session_state[f"verify_tat_informed_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_tat_informed
            )
            st.session_state[f"verify_ready_to_issue_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_ready_to_issue
            )
            st.session_state[f"verify_conformity_statement_{s.sr_no}"] = _bool_to_yn_choice(
                s.verify_conformity_statement
            )
        if not rows:
            rows = _default_sample_rows()
        _reset_sample_editor(pd.DataFrame(rows))
        if request.samples:
            first_cat = normalize_category(request.samples[0].category)
            cats = all_sample_categories()
            st.session_state["sample_category_select"] = cats.get(
                first_cat, list(cats.values())[0]
            )


def apply_request_prefill(request: TestRequestData) -> None:
    """Load a saved request into CTR form session keys before widgets render."""
    _sync_request_prefill(request)
    _sync_customer_prefill(request.customer)


def clear_ctr_form_state() -> None:
    """Remove CTR intake widget keys so a fresh form can be created."""
    prefixes = (
        "f_",
        "ctr_c",
        "workflow_",
        "custom_tests_sr_",
        "intake_",
        "verify_",
        "test_package_type_",
        "parameters_other_",
        "food_parameters_",
        "cust_master_",
        "ctr_edit_",
    )
    exact = {
        "_prefill_request_key",
        "_prefill_customer_key",
        "_prefill_contacts_key",
        "_gst_autoload_last",
        "customer_gst_autoload_msg",
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
    sample_first: bool = False,
    include_customer_picker: bool = False,
    customer_from_master: bool = False,
    pinned_package_id: int | None = None,
    submit_label: str = "Save & Generate Form",
    actor=None,
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
        default_test_keys_for_category,
        get_test,
        normalize_category,
    )
    from services.sample_categories import category_select_options
    from services.test_packages import (
        CTR_PARAMETER_OPTIONS,
        CTR_PARAMETER_OTHER,
        is_other_parameters_label,
    )

    report_format_options = list(REPORT_FORMAT_LABELS.values())

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
            if not sample_name:
                return []
            try:
                sr_no = int(row.get("Sr. No") or 0)
            except (TypeError, ValueError):
                sr_no = 0
            resolved = _food_resolved_for_row(row, row_category)
            if resolved is None:
                return []
            wl = list(st.session_state.get(f"intake_wl_keys_{sr_no}", []))
            nwl = list(st.session_state.get(f"intake_nwl_keys_{sr_no}", []))
            fmt = report_format
            if fmt == REPORT_FORMAT_WITH_LOGO:
                return wl
            if fmt == REPORT_FORMAT_WITHOUT_LOGO:
                return nwl
            return _merge_test_keys(wl, nwl)
        return []

    def _custom_options_for_row(row: dict, category: str) -> dict[str, str]:
        row_category = normalize_category(category)
        ptype_key = ""
        if row_category == CATEGORY_FOOD:
            resolved = _food_resolved_for_row(row, row_category)
            ptype_key = (resolved.package_type if resolved else "") or ""
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

    if pinned_package_id is not None:
        st.session_state["intake_pinned_package_id"] = int(pinned_package_id)

    customer_prefill = prefill
    if not sample_first and not customer_from_master:
        p = _sync_customer_prefill(prefill)

    cat_options = category_select_options()
    cat_keys = [k for k, _ in cat_options]
    cat_labels = [lbl for _, lbl in cat_options]
    cat_key_by_label = {lbl: key for key, lbl in cat_options}
    editor_preview = _sample_editor_df_for_render()
    row_categories = [
        _category_key_from_row(row, cat_key_by_label)
        for row in editor_preview.to_dict(orient="records")
        if _sample_row_nonempty(row)
    ] or [CATEGORY_FOOD]
    filter_category = row_categories[0]
    food_package_first = (
        not edit_mode and CATEGORY_FOOD in row_categories
    )
    sec = ctr_section_numbers(
        sample_first=sample_first,
        include_customer_picker=include_customer_picker,
        filter_category=filter_category,
        food_package_first=food_package_first,
    )

    if filter_category == CATEGORY_WATER:
        st.info(
            "All **13 water protocol tests** are included automatically "
            "(11 chemical + 2 microbiological on the last Observation Table page). "
            f"Assign a **chemical analyst** and a **micro analyst** in "
            f"Section {sec['lab_workflow']}."
        )
    elif filter_category == CATEGORY_MICRO:
        st.info(
            "All **6 microbiological tests** are included automatically "
            "(Total Plate Count, T.coliform, E. Coli, Salmonella, "
            "Staphylococcus aureus, Yeast and Mould)."
        )
    elif filter_category == CATEGORY_FOOD:
        if food_package_first:
            st.info(
                "**Step 1:** Enter each sample **product name** in the table below. "
                "If no test package exists, create it under **Test packages** "
                "(your customer details are kept when you switch workspace). "
                "**Step 2:** After every product has a defined package, fill customer details."
            )
        else:
            st.info(
                "For each **Food** row: enter sample name (e.g. Jaggery, Masala). "
                "Tests load from that product's test package — pick report format "
                "and with-logo / without-logo tests. **Parameters** (FSSAI / Nutrition / Other) "
                "is what prints in the CTR Parameters column only."
            )
    else:
        st.info(
            f"No catalog tests are defined yet for **{selected_cat_label}**. "
            "Assign custom formulas from Admin for this category."
        )

    from services.users import analyst_display_label, list_active_analysts

    analysts = list_active_analysts()
    analyst_options = [analyst_display_label(u) for u in analysts]
    label_to_id = {analyst_display_label(u): u.id for u in analysts}

    if not analyst_options:
        st.error("No active analyst users — create one in Admin before saving samples.")

    p_holder: list[Optional[Customer]] = [
        _sync_customer_prefill(prefill) if not sample_first else None
    ]

    def _render_customer_sections() -> int:
        nonlocal customer_prefill
        if include_customer_picker:
            picked = customer_picker(
                lookup_no=sec["customer_lookup"],
                customer_details_no=sec["customer_details"],
                key_prefix="ctr_edit_",
            )
            if picked is not None:
                customer_prefill = picked
            st.divider()
            if customer_prefill is not None:
                render_section_title(
                    "Edit reason (customer updates)",
                    "Required if you change permanent customer details for an existing GST record.",
                )
                edit_reason_field(key="new_ctr_customer_edit_reason")

        p_holder[0] = _sync_customer_prefill(customer_prefill)

        printed_sections = (
            f"Sections {sec['customer_details']}, {sec['request_details']}, "
            f"and {sec['sample_table']}"
        )
        st.markdown(
            f'<div class="sls-hint"><b>{printed_sections} — Customer Test Request '
            "(printed form)</b> — Fields below match the printed CTR (LLP.docx).</div>",
            unsafe_allow_html=True,
        )
        return render_customer_details_form(
            section_no=sec["customer_details"],
            show_gst_autoload=True,
        )

    def _render_request_details_section() -> None:
        render_section_title(
            f"{sec['request_details']}. Test request details",
            "Date, sampling, service, and payment fields printed on the CTR form.",
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

        st.text_area(
            "Payment Details",
            placeholder="Advance amount, UTR, billing notes…",
            height=70,
            key="f_payment_details",
        )

    def _render_lab_code_section() -> None:
        render_section_title(
            f"{sec['lab_code']}. Lab code",
            "Printed on the CTR form. Sample IDs in the lab workflow section "
            "are derived from this code.",
        )
        st.text_input(
            "Lab Code *",
            key="f_lab_code",
            placeholder="e.g. SLS/26/306",
            help=(
                "Sample IDs use this code with /01, /02 for each row "
                f"(see Section {sec['lab_workflow']})."
            ),
        )

    @st.fragment
    def _sample_workflow_fragment(*, phase: str = "all") -> None:
        """Sample table and lab workflow — reruns live on edit."""
        run_table = phase in ("all", "table")
        run_workflow = phase in ("all", "workflow")

        if run_table:
            render_section_title(
                f"{sec['sample_table']}. Sample table",
                "Matches the printed CTR form: Sr. No, Name of sample, Code/batch no., "
                "and Sample qty. For **Food**, choose Parameters under each sample below. "
                "Code/batch no. is optional customer reference.",
            )

        default_rows = _default_sample_rows()
        if run_table:
            editor_df = _sample_editor_df_for_render()
            st.session_state[_SAMPLE_EDITOR_KEY] = editor_df
            if _SAMPLE_EDITOR_WIDGET_KEY not in st.session_state:
                st.session_state[_SAMPLE_EDITOR_KEY] = _migrate_sample_editor_df(
                    editor_df, filter_category
                )
                editor_df = st.session_state[_SAMPLE_EDITOR_KEY]

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

            category_column = {
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=cat_labels,
                    required=True,
                ),
            }
            if filter_category == CATEGORY_FOOD:
                column_config = {
                    "Sr. No": st.column_config.NumberColumn("Sr. No", min_value=1, step=1),
                    **category_column,
                    "Name of sample": st.column_config.TextColumn("Name of sample"),
                    "Code/batch no.": st.column_config.TextColumn(
                        "Code/batch no.",
                        help="Customer batch/reference; optional; may repeat across rows.",
                    ),
                    "Sample qty.": st.column_config.TextColumn("Sample qty."),
                    "Parameters": None,
                    "_sample_id": None,
                    "_status": None,
                }
            else:
                if filter_category == CATEGORY_WATER:
                    parameters_column = {
                        "Parameters": st.column_config.TextColumn(
                            "Parameters",
                            disabled=True,
                            help="Water: 11 chemical + 2 micro protocol tests are included automatically.",
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
                column_config = {
                    "Sr. No": st.column_config.NumberColumn("Sr. No", min_value=1, step=1),
                    **category_column,
                    "Name of sample": st.column_config.TextColumn("Name of sample"),
                    "Code/batch no.": st.column_config.TextColumn(
                        "Code/batch no.",
                        help="Customer batch/reference; optional; may repeat across rows.",
                    ),
                    "Sample qty.": st.column_config.TextColumn("Sample qty."),
                    **parameters_column,
                    "_sample_id": None,
                    "_status": None,
                }

            sample_df = st.data_editor(
                editor_df,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
                key=_SAMPLE_EDITOR_WIDGET_KEY,
                disabled=not analyst_options,
            )
            sample_df = _normalize_ctr_df(sample_df)
            st.session_state[_SAMPLE_EDITOR_KEY] = sample_df
            st.session_state[_SAMPLE_EDITOR_LIVE_KEY] = sample_df

            for row in sample_df.to_dict(orient="records"):
                if normalize_category(filter_category) != CATEGORY_FOOD:
                    continue
                sample_name = _cell_text(row.get("Name of sample")).strip()
                try:
                    sr_no = int(row.get("Sr. No") or 0)
                except (TypeError, ValueError):
                    sr_no = 0
                if not sample_name:
                    if _sample_row_nonempty(row):
                        st.caption(f"Sr. {sr_no}: enter sample name to load tests.")
                    continue
                status = str(row.get("_status") or "pending")
                locked = status != "pending"
                st.markdown(f"**Sr. {sr_no} — Sample & tests**")
                parameters_label = _render_food_parameters_for_row(
                    sr_no=sr_no,
                    row=row,
                    locked=locked,
                )
                custom_count = len(
                    st.session_state.get(f"custom_tests_sr_{sr_no}", [])
                )
                resolved = _render_food_sample_package_block(
                    sr_no=sr_no,
                    sample_name=sample_name,
                    parameters_label=parameters_label,
                    filter_category=filter_category,
                    custom_count=custom_count,
                    actor=actor,
                )
                if resolved:
                    _render_food_intake_test_selection(
                        sr_no=sr_no,
                        resolved=resolved,
                        locked=locked,
                        report_format_options=report_format_options,
                    )
                    options = _custom_options_for_row(row, filter_category)
                    if options:
                        st.multiselect(
                            f"Sr. {sr_no}: Additional formulas",
                            options=list(options.keys()),
                            key=f"custom_tests_sr_{sr_no}",
                            disabled=locked,
                            help="Optional custom tests from Admin for this category.",
                        )
                    fmt_label = str(
                        st.session_state.get(
                            f"workflow_report_format_{sr_no}",
                            REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
                        )
                    ).strip()
                    fmt_key = LABEL_TO_REPORT_FORMAT.get(
                        fmt_label, REPORT_FORMAT_WITH_LOGO
                    )
                    wl_keys = list(st.session_state.get(f"intake_wl_keys_{sr_no}", []))
                    nwl_keys = list(st.session_state.get(f"intake_nwl_keys_{sr_no}", []))
                    if fmt_key == REPORT_FORMAT_WITH_LOGO:
                        names = ", ".join(get_test(k).name for k in wl_keys)
                        st.caption(f"Tests selected (with logo): {names or '—'}")
                    elif fmt_key == REPORT_FORMAT_WITHOUT_LOGO:
                        names = ", ".join(get_test(k).name for k in nwl_keys)
                        st.caption(f"Tests selected (without logo): {names or '—'}")
                    else:
                        wl = ", ".join(get_test(k).name for k in wl_keys)
                        nwl = ", ".join(get_test(k).name for k in nwl_keys)
                        st.caption(f"With-logo tests selected: {wl or '—'}")
                        st.caption(f"Without-logo tests selected: {nwl or '—'}")

        if run_workflow:
            sample_df = _normalize_ctr_df(_current_sample_editor_df())

            pinned_by_sr: dict[int, tuple[Optional[int], Optional[int]]] = {}
            if edit_mode and request_prefill is not None:
                for s in request_prefill.samples:
                    if getattr(s, "package_id", None) is not None:
                        pinned_by_sr[s.sr_no] = (
                            s.package_id,
                            getattr(s, "package_version_no", None),
                        )

            st.markdown(
                f'<div class="sls-hint"><b>Section {sec["lab_workflow"]} — Lab workflow '
                "(not printed)</b> — Sample ID and analyst assignment for internal "
                "lab handoff only.</div>",
                unsafe_allow_html=True,
            )
            render_section_title(
                f"{sec['lab_workflow']}. Lab workflow",
                "Sample ID is auto-generated from the Lab Code "
                "(e.g. SLS/26/306/01, /02 for each sample on the request). "
                "Enter protocol number and assign analyst below.",
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

                row_category = _category_key_from_row(row, cat_key_by_label)
                if row_category != CATEGORY_FOOD:
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
                if row_category == CATEGORY_FOOD:
                    st.text_input(
                        "Protocol No *",
                        key=f"workflow_protocol_no_{sr_no}",
                        disabled=locked,
                        help="Printed on the analyst protocol document.",
                    )
                else:
                    p_col, r_col = st.columns(2)
                    with p_col:
                        st.text_input(
                            "Protocol No *",
                            key=f"workflow_protocol_no_{sr_no}",
                            disabled=locked,
                            help="Printed on the analyst protocol document.",
                        )
                    with r_col:
                        st.selectbox(
                            "Report format *",
                            options=report_format_options,
                            key=f"workflow_report_format_{sr_no}",
                            disabled=locked,
                            help=(
                                "A uses with-logo tests; B uses without-logo; "
                                "Both stores both sets separately."
                            ),
                        )
                if row_category == CATEGORY_WATER:
                    chem_col, micro_col = st.columns(2)
                    with chem_col:
                        st.selectbox(
                            "Chemical analyst *",
                            options=analyst_select_options,
                            key=f"workflow_analyst_{sr_no}",
                            disabled=locked or not analyst_options,
                            help="Performs the 11 chemical water tests.",
                        )
                    with micro_col:
                        st.selectbox(
                            "Micro analyst *",
                            options=analyst_select_options,
                            key=f"workflow_micro_analyst_{sr_no}",
                            disabled=locked or not analyst_options,
                            help="Performs Total Coliform and E. coli on the last page.",
                        )
                else:
                    st.selectbox(
                        "Assigned analyst *",
                        options=analyst_select_options,
                        key=f"workflow_analyst_{sr_no}",
                        disabled=locked or not analyst_options,
                    )

                if row_category != CATEGORY_FOOD:
                    options = _custom_options_for_row(row, filter_category)
                    if options:
                        st.multiselect(
                            f"Sr. {sr_no}: Additional formulas",
                            options=list(options.keys()),
                            key=f"custom_tests_sr_{sr_no}",
                            disabled=locked,
                            help="Optional custom tests from Admin for this category.",
                        )

                if row_category != CATEGORY_FOOD:
                    fmt_label = str(
                        st.session_state.get(
                            f"workflow_report_format_{sr_no}",
                            REPORT_FORMAT_LABELS[REPORT_FORMAT_WITH_LOGO],
                        )
                    ).strip()
                    fmt_key = LABEL_TO_REPORT_FORMAT.get(
                        fmt_label, REPORT_FORMAT_WITH_LOGO
                    )
                    row_keys = _row_test_keys(
                        row, filter_category, report_format=fmt_key
                    )
                    names = ", ".join(get_test(k).name for k in row_keys)
                    st.caption(f"Tests included: {names or '—'}")

                if f"verify_review_date_{sr_no}" not in st.session_state:
                    st.session_state[f"verify_review_date_{sr_no}"] = (
                        st.session_state.get("f_request_date")
                    )
                if f"verify_lab_code_{sr_no}" not in st.session_state:
                    st.session_state[f"verify_lab_code_{sr_no}"] = str(
                        st.session_state.get("f_lab_code", "") or ""
                    )
                sync_verify_sample_code(
                    derived_codes.get(sr_no, ""),
                    session=st.session_state,
                    sr_no=sr_no,
                )
                st.markdown("**Test request details (this sample)**")
                rd1, rd2 = st.columns(2)
                with rd1:
                    st.selectbox(
                        "Storage Temperature",
                        options=[""] + list(STORAGE_TEMPERATURE_OPTIONS),
                        format_func=lambda x: "Not specified" if x == "" else x,
                        key=f"f_storage_temperature_{sr_no}",
                        disabled=locked,
                    )
                    if (
                        st.session_state.get(f"f_storage_temperature_{sr_no}")
                        == STORAGE_TEMPERATURE_OTHER
                    ):
                        st.text_input(
                            "Storage temperature (other)",
                            key=f"f_storage_temperature_other_{sr_no}",
                            disabled=locked,
                        )
                    st.radio(
                        "Sampling Done by Laboratory",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"f_sampling_choice_{sr_no}",
                        disabled=locked,
                    )
                with rd2:
                    st.radio(
                        "Service required",
                        options=["", "Urgent", "Regular"],
                        format_func=lambda x: "Not specified" if x == "" else x,
                        horizontal=True,
                        key=f"f_service_type_{sr_no}",
                        disabled=locked,
                    )
                    st.multiselect(
                        "Mode of report delivery",
                        options=DELIVERY_MODE_OPTIONS,
                        key=f"f_delivery_mode_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "Decision Rule required",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"f_decision_choice_{sr_no}",
                        disabled=locked,
                    )
                st.text_area(
                    "Specific test method / Specification",
                    height=60,
                    key=f"f_test_method_spec_{sr_no}",
                    disabled=locked,
                )
                st.markdown("**Sample verification (printed on checklist)**")
                v1, v2, v3 = st.columns(3)
                with v1:
                    st.date_input(
                        "Review Date *",
                        key=f"verify_review_date_{sr_no}",
                        disabled=locked,
                    )
                with v2:
                    st.text_input(
                        "Lab Code *",
                        key=f"verify_lab_code_{sr_no}",
                        disabled=locked,
                    )
                with v3:
                    st.text_input(
                        "Sample Code",
                        key=f"verify_sample_code_{sr_no}",
                        disabled=True,
                        help="Auto-filled from registration sample ID.",
                    )
                st.text_input(
                    "Sample condition *",
                    key=f"verify_sample_condition_{sr_no}",
                    disabled=locked,
                )
                v3, v4 = st.columns(2)
                with v3:
                    st.radio(
                        "Checked for Sample Quantity *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_qty_checked_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "Checked for Availability of Chemical *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_chemical_available_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "Checked for Availability of Methods *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_methods_available_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "Informed testing Methods to Customer *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_methods_informed_{sr_no}",
                        disabled=locked,
                    )
                with v4:
                    st.radio(
                        "Informed turnaround time to Customer *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_tat_informed_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "Sample is ready to issue *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_ready_to_issue_{sr_no}",
                        disabled=locked,
                    )
                    st.radio(
                        "About statement of conformity *",
                        options=["Not specified", "Yes", "No"],
                        horizontal=True,
                        key=f"verify_conformity_statement_{sr_no}",
                        disabled=locked,
                    )

    if food_package_first:
        _sample_workflow_fragment(phase="table")
        sample_rows = _current_sample_editor_df().to_dict(orient="records")
        packages_ready, blocked = food_intake_packages_ready(
            sample_rows, filter_category
        )
        if not packages_ready:
            st.warning(
                "Define test packages for these products first (Sample registration tab), "
                "then continue with request details."
            )
            for item in blocked:
                st.markdown(f"- {item}")
            return None

        if customer_from_master:
            contact_count = 1
        else:
            contact_count = _render_customer_sections()
        _render_request_details_section()
        _render_lab_code_section()
        _sample_workflow_fragment(phase="workflow")
    else:
        if customer_from_master:
            contact_count = 1
        else:
            contact_count = _render_customer_sections()
        _render_request_details_section()
        _render_lab_code_section()
        _sample_workflow_fragment(phase="all")

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
    delivery_mode = format_delivery_modes(st.session_state.get("f_delivery_mode", []))
    storage_temperature = storage_temperature_for_save(
        str(st.session_state.get("f_storage_temperature", "") or ""),
        str(st.session_state.get("f_storage_temperature_other", "") or ""),
    )
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

    def _yn_local(choice: str) -> Optional[bool]:
        if choice == "Yes":
            return True
        if choice == "No":
            return False
        return None

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
        row_category = _category_key_from_row(row, cat_key_by_label)
        row_keys = _row_test_keys(row, row_category, report_format=report_format)
        params_text = _cell_text(row.get("Parameters")).strip()
        parameters_select = params_text
        resolved = None
        sample_name = _cell_text(row.get("Name of sample")).strip()
        ptype = None
        parameters_field = params_text
        if row_category == CATEGORY_FOOD and sample_name:
            params_text = _food_parameters_label_for_row(sr_no, row)
            parameters_select = params_text
            parameters_field = params_text
            if is_other_parameters_label(params_text):
                parameters_field = str(
                    st.session_state.get(f"parameters_other_{sr_no}", "") or ""
                ).strip()
            resolved = _food_resolved_for_row(row, row_category)
            ptype = resolved.package_type if resolved else None
        tests_with_logo: list[str] = []
        tests_without_logo: list[str] = []
        if row_category == CATEGORY_FOOD:
            tests_with_logo = list(
                st.session_state.get(f"intake_wl_keys_{sr_no}", [])
            )
            tests_without_logo = list(
                st.session_state.get(f"intake_nwl_keys_{sr_no}", [])
            )
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
        micro_label = str(
            st.session_state.get(f"workflow_micro_analyst_{sr_no}", "") or ""
        ).strip()
        assigned_micro_analyst_id = (
            label_to_id.get(micro_label)
            if row_category == CATEGORY_WATER
            else None
        )
        old_sample = None
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
        if locked and edit_mode and old_sample is not None:
            verify_review_date = old_sample.verify_review_date
            verify_lab_code = old_sample.verify_lab_code or ""
            verify_sample_condition = old_sample.verify_sample_condition or ""
            verify_qty_checked = old_sample.verify_qty_checked
            verify_chemical_available = old_sample.verify_chemical_available
            verify_methods_available = old_sample.verify_methods_available
            verify_methods_informed = old_sample.verify_methods_informed
            verify_tat_informed = old_sample.verify_tat_informed
            verify_ready_to_issue = old_sample.verify_ready_to_issue
            verify_conformity_statement = old_sample.verify_conformity_statement
        else:
            verify_review_date = st.session_state.get(f"verify_review_date_{sr_no}")
            verify_lab_code = str(
                st.session_state.get(f"verify_lab_code_{sr_no}", "") or ""
            ).strip()
            verify_sample_code = str(
                st.session_state.get(f"verify_sample_code_{sr_no}", "") or ""
            ).strip()
            verify_sample_condition = str(
                st.session_state.get(f"verify_sample_condition_{sr_no}", "") or ""
            ).strip()
            verify_qty_checked = _yn_choice_to_bool(
                str(st.session_state.get(f"verify_qty_checked_{sr_no}", "") or "")
            )
            verify_chemical_available = _yn_choice_to_bool(
                str(
                    st.session_state.get(f"verify_chemical_available_{sr_no}", "")
                    or ""
                )
            )
            verify_methods_available = _yn_choice_to_bool(
                str(
                    st.session_state.get(f"verify_methods_available_{sr_no}", "")
                    or ""
                )
            )
            verify_methods_informed = _yn_choice_to_bool(
                str(
                    st.session_state.get(f"verify_methods_informed_{sr_no}", "")
                    or ""
                )
            )
            verify_tat_informed = _yn_choice_to_bool(
                str(st.session_state.get(f"verify_tat_informed_{sr_no}", "") or "")
            )
            verify_ready_to_issue = _yn_choice_to_bool(
                str(st.session_state.get(f"verify_ready_to_issue_{sr_no}", "") or "")
            )
            verify_conformity_statement = _yn_choice_to_bool(
                str(
                    st.session_state.get(f"verify_conformity_statement_{sr_no}", "")
                    or ""
                )
            )
        row_storage = storage_temperature_for_save(
            str(st.session_state.get(f"f_storage_temperature_{sr_no}", "") or ""),
            str(st.session_state.get(f"f_storage_temperature_other_{sr_no}", "") or ""),
        )
        samples.append(
            SampleRow(
                id=sample_id,
                sr_no=sr_no,
                sample_name=_cell_text(row.get("Name of sample")),
                batch_code=_cell_text(row.get("Code/batch no.")),
                quantity=_cell_text(row.get("Sample qty.")),
                parameters=parameters_field if row_category == CATEGORY_FOOD else (
                    display_names if row_category not in (CATEGORY_WATER, CATEGORY_MICRO)
                    else params_text
                ),
                test_keys=list(row_keys),
                category=row_category,
                status=status,
                assigned_analyst_id=assigned_analyst_id,
                assigned_micro_analyst_id=assigned_micro_analyst_id,
                protocol_no=protocol_no,
                report_format=report_format,
                tests_with_logo=tests_with_logo,
                tests_without_logo=tests_without_logo,
                package_id=resolved.package_id if resolved else None,
                package_version_no=resolved.package_version_no if resolved else None,
                package_type=ptype if row_category == CATEGORY_FOOD else None,
                parameters_select=parameters_select if row_category == CATEGORY_FOOD else "",
                storage_temperature=row_storage,
                sampling_by_lab=_yn_local(
                    str(st.session_state.get(f"f_sampling_choice_{sr_no}", "") or "")
                ),
                decision_rule=_yn_local(
                    str(st.session_state.get(f"f_decision_choice_{sr_no}", "") or "")
                ),
                service_type=str(
                    st.session_state.get(f"f_service_type_{sr_no}", "") or ""
                ),
                delivery_mode=format_delivery_modes(
                    st.session_state.get(f"f_delivery_mode_{sr_no}", [])
                ),
                test_method_spec=str(
                    st.session_state.get(f"f_test_method_spec_{sr_no}", "") or ""
                ),
                verify_review_date=verify_review_date,
                verify_lab_code=verify_lab_code,
                verify_sample_code=verify_sample_code,
                verify_sample_condition=verify_sample_condition,
                verify_qty_checked=verify_qty_checked,
                verify_chemical_available=verify_chemical_available,
                verify_methods_available=verify_methods_available,
                verify_methods_informed=verify_methods_informed,
                verify_tat_informed=verify_tat_informed,
                verify_ready_to_issue=verify_ready_to_issue,
                verify_conformity_statement=verify_conformity_statement,
            )
        )

    if customer_from_master and not edit_mode:
        from services.customers import get_customer_by_id

        cust_id = st.session_state.get("intake_customer_id")
        if not cust_id:
            st.error("Select a customer in the Customers tab or above before saving.")
            return None
        customer = get_customer_by_id(int(cust_id))
        if customer is None:
            st.error("Selected customer was not found. Pick another customer.")
            return None
    else:
        contacts = _read_contacts_from_session(contact_count)
        primary = contacts[0] if contacts else ContactPerson()
        p = p_holder[0] or _sync_customer_prefill(customer_prefill)
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
        sampling_by_lab=None,
        storage_temperature="",
        test_method_spec="",
        decision_rule=None,
        service_type="",
        delivery_mode="",
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
