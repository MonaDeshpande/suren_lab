"""
services/requests.py
--------------------
Save a full Customer Test Request (header + sample rows) after the form is submitted.

Flow:
  1. Upsert permanent customer (see customers.py)
  2. Insert one test_requests row
  3. Insert request_samples rows with reception-entered sample_code (10-day expiry)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import json

from db.connection import get_db
from services.audit import actor_display_name, log_from_user
from services.customers import Customer, get_customer_by_id, upsert_customer
from services.samples import (
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITHOUT_LOGO,
    REPORT_FORMAT_WITH_LOGO,
    REPORT_FORMATS,
    allocate_sample_code,
    derive_sample_code,
    is_valid_sample_code_format,
    normalize_report_format,
    normalize_sample_code,
)
from services.users import (
    analyst_full_name,
    assert_valid_analyst_assignee,
    list_active_analysts,
)
from services.versions import request_snapshot, save_version, validate_edit_reason
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    TEST_CATALOG,
    filter_keys_for_category,
    has_mixed_food_families,
    normalize_category,
    tests_for_category,
)
from services.test_packages import (
    ctr_parameters_label_for_sample,
    is_other_parameters_label,
    normalize_package_type,
    package_display_label,
    package_type_label,
    parameters_label_to_package_type,
    resolve_package_for_product,
    resolve_package_tests,
)
from services.protocol_store import sync_reception_protocol_header
from services.test_packages import _merge_test_key_lists


@dataclass
class SampleRow:
    """One line in the 'Sample Description & tests to be performed' table."""

    sr_no: int
    sample_name: str = ""
    batch_code: str = ""
    quantity: str = ""
    parameters: str = ""  # joined display names for CTR PDF
    test_keys: list[str] = field(default_factory=list)  # shared catalog keys
    category: str = "food"  # food | water | cattle_feed_fertilizer

    # Populated after save / load
    sample_code: str = ""
    id: Optional[int] = None
    status: str = "pending"
    assigned_analyst_id: Optional[int] = None
    assigned_analyst_name: str = ""
    assigned_micro_analyst_id: Optional[int] = None
    assigned_micro_analyst_name: str = ""
    protocol_no: str = ""
    report_format: str = REPORT_FORMAT_WITH_LOGO
    tests_with_logo: list[str] = field(default_factory=list)
    tests_without_logo: list[str] = field(default_factory=list)
    package_id: Optional[int] = None
    package_version_no: Optional[int] = None
    package_type: Optional[str] = None

    # Sample verification checklist (per sample, printed on last CTR page(s))
    verify_review_date: Optional[date] = None
    verify_lab_code: str = ""
    verify_sample_condition: str = ""
    verify_qty_checked: Optional[bool] = None
    verify_chemical_available: Optional[bool] = None
    verify_methods_available: Optional[bool] = None
    verify_methods_informed: Optional[bool] = None
    verify_tat_informed: Optional[bool] = None
    verify_ready_to_issue: Optional[bool] = None
    verify_conformity_statement: Optional[bool] = None

    def is_empty(self) -> bool:
        """True when the user left this sample row blank."""
        if normalize_category(self.category) == CATEGORY_FOOD:
            return not any(
                [
                    (self.sample_name or "").strip(),
                    (self.quantity or "").strip(),
                ]
            )
        return not any(
            [
                (self.sample_name or "").strip(),
                (self.quantity or "").strip(),
                (self.parameters or "").strip(),
                list(self.test_keys or []),
            ]
        )


def ctr_parameters_display(sample: SampleRow) -> str:
    """Short Parameters text for printed CTR (not the full stored parameters string)."""
    cat = normalize_category(sample.category)
    if cat == CATEGORY_FOOD:
        return ctr_parameters_label_for_sample(
            parameters=sample.parameters,
            package_type=sample.package_type,
        )
    if cat == CATEGORY_WATER:
        return ""
    if cat == CATEGORY_MICRO:
        return ""
    return (sample.parameters or "").strip()


def _verification_tuple(sample: SampleRow) -> tuple:
    """DB bind values for verification checklist columns."""
    return (
        sample.verify_review_date,
        (sample.verify_lab_code or "").strip() or None,
        (sample.verify_sample_condition or "").strip() or None,
        sample.verify_qty_checked,
        sample.verify_chemical_available,
        sample.verify_methods_available,
        sample.verify_methods_informed,
        sample.verify_tat_informed,
        sample.verify_ready_to_issue,
        sample.verify_conformity_statement,
    )


@dataclass
class TestRequestData:
    """
    Complete payload collected from the Streamlit form.

    Permanent customer fields live on `customer`.
    Everything else is request-specific.
    """

    customer: Customer

    request_date: Optional[date] = None
    lab_code: str = ""

    number_of_samples: Optional[int] = None
    sampling_by_lab: Optional[bool] = None  # Yes / No / unset
    storage_temperature: str = ""
    test_method_spec: str = ""
    decision_rule: Optional[bool] = None  # Yes / No / unset
    service_type: str = ""  # Urgent | Regular | ""
    delivery_mode: str = ""  # Collect | Courier | Email/Whatsapp
    payment_details: str = ""
    sample_description: str = ""

    samples: list[SampleRow] = field(default_factory=list)

    # Filled after save
    request_id: Optional[int] = None


STORAGE_TEMPERATURE_OTHER = "Other"
STORAGE_TEMPERATURE_OPTIONS = [
    "2°C to 8°C",
    "4°C",
    "Room Temp",
    STORAGE_TEMPERATURE_OTHER,
]
_CANONICAL_STORAGE_TEMPERATURES = frozenset(
    opt for opt in STORAGE_TEMPERATURE_OPTIONS if opt != STORAGE_TEMPERATURE_OTHER
)


def storage_temperature_select_value(stored: str | None) -> str:
    """Map a stored value to the Reception selectbox option."""
    text = (stored or "").strip()
    if not text:
        return ""
    if text in _CANONICAL_STORAGE_TEMPERATURES:
        return text
    return STORAGE_TEMPERATURE_OTHER


def storage_temperature_for_save(
    select_value: str,
    other_text: str | None,
) -> str:
    """Merge selectbox + Other text into the value stored on the request."""
    choice = (select_value or "").strip()
    if not choice:
        return ""
    if choice == STORAGE_TEMPERATURE_OTHER:
        return (other_text or "").strip()
    return choice


DELIVERY_MODE_OPTIONS = ["Collect", "Courier", "Email/Whatsapp"]
_DELIVERY_MODE_ALIASES = {
    "collect": "Collect",
    "courier": "Courier",
    "email/whatsapp": "Email/Whatsapp",
    "email": "Email/Whatsapp",
    "whatsapp": "Email/Whatsapp",
}


def _canonical_delivery_mode(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if text in DELIVERY_MODE_OPTIONS:
        return text
    return _DELIVERY_MODE_ALIASES.get(text.lower())


def parse_delivery_modes(stored: str | None) -> list[str]:
    """Parse a stored delivery_mode string into canonical multiselect values."""
    text = (stored or "").strip()
    if not text:
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        canonical = _canonical_delivery_mode(part)
        if canonical and canonical not in seen:
            seen.add(canonical)
            selected.append(canonical)
    return [opt for opt in DELIVERY_MODE_OPTIONS if opt in seen]


def format_delivery_modes(modes: list[str] | None) -> str:
    """Serialize multiselect values for storage on test_requests."""
    if not modes:
        return ""
    selected: list[str] = []
    seen: set[str] = set()
    for mode in modes:
        canonical = _canonical_delivery_mode(str(mode))
        if canonical and canonical not in seen:
            seen.add(canonical)
            selected.append(canonical)
    ordered = [opt for opt in DELIVERY_MODE_OPTIONS if opt in seen]
    return ", ".join(ordered)


def delivery_mode_is_selected(stored: str | None, option: str) -> bool:
    """True when a delivery option is included in the stored value."""
    canonical = _canonical_delivery_mode(option)
    if not canonical:
        return False
    return canonical in parse_delivery_modes(stored)


def assign_derived_sample_codes(
    data: TestRequestData,
    existing: TestRequestData | None = None,
) -> None:
    """
    Set sample_code on each non-empty row from lab_code and enumeration order.

    Locked samples (status != pending) keep their stored sample_code on edit.
    """
    existing_by_id: dict[int, SampleRow] = {}
    if existing:
        existing_by_id = {
            s.id: s for s in existing.samples if s.id is not None
        }

    filled = sorted(
        [s for s in data.samples if not s.is_empty()],
        key=lambda s: s.sr_no,
    )
    total = len(filled)
    for index, sample in enumerate(filled, start=1):
        old = existing_by_id.get(sample.id) if sample.id is not None else None
        if old and old.status != "pending":
            sample.sample_code = old.sample_code or ""
        else:
            sample.sample_code = derive_sample_code(
                data.lab_code,
                index=index,
                total=total,
            )


@dataclass
class RequestSummary:
    """Lightweight row for searching existing test requests."""

    request_id: int
    lab_code: str
    request_date: Optional[date]
    customer_name: str
    sample_count: int
    sample_codes: str


def _tests_with_logo_json_for_save(sample: SampleRow) -> Optional[str]:
    """Serialize with-logo test keys for storage."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITHOUT_LOGO:
        return None
    keys = [k for k in (sample.tests_with_logo or []) if k]
    return json.dumps(keys) if keys else None


def _tests_without_logo_json_for_save(sample: SampleRow) -> Optional[str]:
    """Serialize without-logo test keys for storage."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITH_LOGO:
        return None
    keys = [k for k in (sample.tests_without_logo or []) if k]
    return json.dumps(keys) if keys else None


def _apply_package_report_format_sets(
    sample: SampleRow,
    with_logo_keys: list[str],
    without_logo_keys: list[str],
) -> list[str]:
    """Set per-format logo lists on sample and return analyst test_keys union."""
    fmt = normalize_report_format(sample.report_format)
    wl = list(with_logo_keys)
    nwl = list(without_logo_keys)
    if fmt == REPORT_FORMAT_WITH_LOGO:
        sample.tests_with_logo = wl
        sample.tests_without_logo = []
        return wl
    if fmt == REPORT_FORMAT_WITHOUT_LOGO:
        sample.tests_with_logo = []
        sample.tests_without_logo = nwl
        return nwl
    sample.tests_with_logo = wl
    sample.tests_without_logo = nwl
    return _merge_test_key_lists(wl, nwl)


def _validate_report_format_for_package(
    sr_no: int,
    report_format: str,
    with_logo_keys: list[str],
    without_logo_keys: list[str],
) -> list[str]:
    """Validate report format against intake-selected logo test sets."""
    errors: list[str] = []
    fmt = normalize_report_format(report_format)
    if fmt not in REPORT_FORMATS:
        errors.append(
            f"Sample Sr. {sr_no}: choose a valid report format "
            "(A With Logo, B Without Logo, or Both)."
        )
        return errors
    overlap = set(with_logo_keys) & set(without_logo_keys)
    if overlap:
        names = [
            TEST_CATALOG[k].name for k in sorted(overlap) if k in TEST_CATALOG
        ]
        errors.append(
            f"Sample Sr. {sr_no}: the same test cannot be in both with-logo "
            f"and without-logo lists: {', '.join(names) or ', '.join(sorted(overlap))}."
        )
    if fmt == REPORT_FORMAT_WITH_LOGO and not with_logo_keys:
        errors.append(
            f"Sample Sr. {sr_no}: select at least one with-logo test for "
            "report format A — With Logo."
        )
    elif fmt == REPORT_FORMAT_WITHOUT_LOGO and not without_logo_keys:
        errors.append(
            f"Sample Sr. {sr_no}: select at least one without-logo test for "
            "report format B — Without Logo."
        )
    elif fmt == REPORT_FORMAT_BOTH:
        if not with_logo_keys:
            errors.append(
                f"Sample Sr. {sr_no}: select at least one with-logo test for "
                "report format Both."
            )
        if not without_logo_keys:
            errors.append(
                f"Sample Sr. {sr_no}: select at least one without-logo test for "
                "report format Both."
            )
    return errors


def _validate_intake_tests_in_package(
    sr_no: int,
    selected_keys: list[str],
    allowed_keys: list[str],
) -> list[str]:
    """Ensure intake selections are a subset of the resolved package."""
    allowed = set(allowed_keys)
    invalid = [k for k in selected_keys if k not in allowed]
    if not invalid:
        return []
    names = [TEST_CATALOG[k].name for k in invalid if k in TEST_CATALOG]
    return [
        f"Sample Sr. {sr_no}: invalid test selection outside the package: "
        f"{', '.join(names) or ', '.join(invalid)}."
    ]


def _resolve_sample_tests(
    sample: SampleRow,
    category: str,
) -> tuple[list[str], str, str, Optional[int], Optional[int], Optional[str]]:
    """
    Resolve catalog keys and display text for a sample row.

    Returns (
        test_keys,
        parameters_display,
        tests_to_perform,
        package_id,
        package_version_no,
        package_type,
    ).
    """
    cat = normalize_category(category)
    if cat == CATEGORY_FOOD:
        params_label = (sample.parameters or "").strip()
        ptype = parameters_label_to_package_type(
            params_label
        ) or normalize_package_type(sample.package_type)
        wl = filter_keys_for_category(list(sample.tests_with_logo or []), cat)
        nwl = filter_keys_for_category(list(sample.tests_without_logo or []), cat)

        if is_other_parameters_label(params_label) or (
            ptype is None
            and params_label
            and normalize_package_type(sample.package_type) is None
        ):
            keys = filter_keys_for_category(
                [k for k in (sample.test_keys or []) if k in TEST_CATALOG],
                cat,
            )
            if keys and (wl or nwl):
                keys = _apply_package_report_format_sets(sample, wl, nwl)
            names = [TEST_CATALOG[k].name for k in keys if k in TEST_CATALOG]
            tests_to_perform = ", ".join(names) if names else ""
            parameters_display = ctr_parameters_label_for_sample(
                parameters=sample.parameters,
                package_type=None,
            )
            return keys, parameters_display, tests_to_perform, None, None, None

        resolved = None
        if ptype and (sample.sample_name or "").strip():
            resolved = resolve_package_tests(
                sample.sample_name, ptype, category=cat
            )
        if resolved is None and (sample.sample_name or "").strip():
            resolved = resolve_package_for_product(sample.sample_name, category=cat)

        if resolved:
            keys = _apply_package_report_format_sets(sample, wl, nwl)
            names = [TEST_CATALOG[k].name for k in keys if k in TEST_CATALOG]
            tests_to_perform = ", ".join(names) if names else ""
            parameters_display = package_type_label(ptype or resolved.package_type)
            return (
                keys,
                parameters_display,
                tests_to_perform,
                resolved.package_id,
                resolved.package_version_no,
                ptype or resolved.package_type,
            )

        keys = filter_keys_for_category(
            [k for k in (sample.test_keys or []) if k in TEST_CATALOG],
            cat,
        )
        if keys:
            names = [TEST_CATALOG[k].name for k in keys]
            tests_to_perform = ", ".join(names)
            parameters_display = ctr_parameters_label_for_sample(
                parameters=sample.parameters,
                package_type=sample.package_type,
            )
            return (
                keys,
                parameters_display,
                tests_to_perform,
                sample.package_id,
                sample.package_version_no,
                sample.package_type,
            )
        parameters_display = ctr_parameters_label_for_sample(
            parameters=sample.parameters,
            package_type=sample.package_type,
        )
        return [], parameters_display, "", None, None, sample.package_type

    keys = filter_keys_for_category(
        [k for k in (sample.test_keys or []) if k in TEST_CATALOG],
        cat,
    )
    if keys:
        if cat in (CATEGORY_WATER, CATEGORY_MICRO):
            keys = _apply_package_report_format_sets(sample, keys, keys)
        names = [TEST_CATALOG[k].name for k in keys]
        tests_to_perform = ", ".join(names)
        return keys, tests_to_perform, tests_to_perform, None, None, None
    params = (sample.parameters or "").strip()
    return [], params, params, None, None, None


def _sync_reception_protocol_headers(
    samples: list[SampleRow],
    actor,
    request_date: Optional[date],
) -> None:
    """Push reception protocol no + assignment names into sample_protocols."""
    for sample in samples:
        if sample.id is None:
            continue
        sync_reception_protocol_header(
            sample.id,
            protocol_no=(sample.protocol_no or "").strip(),
            issued_to=(sample.assigned_analyst_name or "").strip(),
            issued_by=actor_display_name(actor),
            sample_received_on=request_date,
            actor=actor,
        )


def save_test_request(
    data: TestRequestData,
    actor=None,
    edit_reason: str | None = None,
) -> TestRequestData:
    """
    Persist customer (permanent) + request + sample rows in one transaction.

    Each non-empty sample gets:
      - auto-derived sample_code from lab code (+ /01, /02 for each sample)
      - tests_to_perform from parameters
      - status = pending
      - expires_at = NOW() + 10 days

    Returns
    -------
    TestRequestData
        Same object with `customer.id`, `request_id`, and each sample's
        `sample_code` populated.
    """
    saved_customer = upsert_customer(
        data.customer,
        edit_reason=edit_reason,
        actor=actor,
    )
    data.customer = saved_customer

    if saved_customer.id is None:
        raise RuntimeError("Customer was saved but no id was returned.")

    samples_to_save = [s for s in data.samples if not s.is_empty()]
    assign_derived_sample_codes(data)

    insert_request_sql = """
        INSERT INTO test_requests (
            customer_id, request_date, lab_code, number_of_samples,
            sampling_by_lab, storage_temperature, test_method_spec,
            decision_rule, service_type, delivery_mode,
            payment_details, sample_description
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
        RETURNING id
    """
    request_values = (
        saved_customer.id,
        data.request_date,
        (data.lab_code or "").strip(),
        data.number_of_samples,
        data.sampling_by_lab,
        (data.storage_temperature or "").strip() or None,
        (data.test_method_spec or "").strip() or None,
        data.decision_rule,
        (data.service_type or "").strip() or None,
        (data.delivery_mode or "").strip() or None,
        (data.payment_details or "").strip() or None,
        (data.sample_description or "").strip() or None,
    )

    insert_sample_sql = """
        INSERT INTO request_samples (
            request_id, sr_no, sample_name, batch_code, quantity, parameters,
            sample_code, category, tests_to_perform, tests_json, status,
            assigned_analyst_id, assigned_micro_analyst_id, protocol_no,
            report_format, tests_with_logo_json,
            tests_without_logo_json, package_id, package_version_no, package_type,
            verify_review_date, verify_lab_code, verify_sample_condition,
            verify_qty_checked, verify_chemical_available, verify_methods_available,
            verify_methods_informed, verify_tat_informed, verify_ready_to_issue,
            verify_conformity_statement,
            expires_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            NOW() + INTERVAL '10 days'
        )
        RETURNING id, sample_code
    """

    saved_samples: list[SampleRow] = []
    analyst_names = {
        u.id: analyst_full_name(u) for u in list_active_analysts()
    }

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_request_sql, request_values)
            request_id = cur.fetchone()[0]

            for sample in samples_to_save:
                assert_valid_analyst_assignee(sample.assigned_analyst_id)
                category = normalize_category(sample.category)
                if category == CATEGORY_WATER:
                    assert_valid_analyst_assignee(sample.assigned_micro_analyst_id)
                    if (
                        sample.assigned_analyst_id
                        and sample.assigned_micro_analyst_id
                        and sample.assigned_analyst_id
                        == sample.assigned_micro_analyst_id
                    ):
                        raise ValueError(
                            f"Sample Sr. {sample.sr_no}: chemical and micro "
                            "analyst must be different users."
                        )
                (
                    keys,
                    parameters_display,
                    tests_to_perform,
                    pkg_id,
                    pkg_ver,
                    pkg_type,
                ) = _resolve_sample_tests(sample, category)
                if keys:
                    tests_json = json.dumps(keys)
                else:
                    tests_json = None
                code = allocate_sample_code(cur, requested=sample.sample_code)
                report_fmt = normalize_report_format(sample.report_format)
                cur.execute(
                    insert_sample_sql,
                    (
                        request_id,
                        sample.sr_no,
                        (sample.sample_name or "").strip() or None,
                        (sample.batch_code or "").strip() or None,
                        (sample.quantity or "").strip() or None,
                        parameters_display or None,
                        code,
                        category,
                        tests_to_perform or None,
                        tests_json,
                        sample.assigned_analyst_id,
                        sample.assigned_micro_analyst_id,
                        (sample.protocol_no or "").strip() or None,
                        report_fmt,
                        _tests_with_logo_json_for_save(sample),
                        _tests_without_logo_json_for_save(sample),
                        pkg_id,
                        pkg_ver,
                        pkg_type,
                        *_verification_tuple(sample),
                    ),
                )
                new_id, returned_code = cur.fetchone()
                sample.id = new_id
                sample.sample_code = returned_code
                sample.category = category
                sample.parameters = parameters_display or ""
                sample.test_keys = keys
                sample.package_id = pkg_id
                sample.package_version_no = pkg_ver
                sample.package_type = pkg_type
                sample.assigned_analyst_name = analyst_names.get(
                    sample.assigned_analyst_id, ""
                )
                sample.assigned_micro_analyst_name = analyst_names.get(
                    sample.assigned_micro_analyst_id, ""
                )
                saved_samples.append(sample)


    data.request_id = request_id
    data.samples = saved_samples
    _sync_reception_protocol_headers(saved_samples, actor, data.request_date)
    codes = ", ".join(s.sample_code for s in saved_samples if s.sample_code)
    log_from_user(
        actor,
        "request.save",
        "test_requests",
        request_id,
        details=f"samples={len(saved_samples)}" + (f" [{codes}]" if codes else ""),
    )
    return data


def get_test_request(request_id: int) -> Optional[TestRequestData]:
    """Load a full test request with customer and sample rows."""
    header_sql = """
        SELECT id, customer_id, request_date, lab_code, number_of_samples,
               sampling_by_lab, storage_temperature, test_method_spec,
               decision_rule, service_type, delivery_mode,
               payment_details, sample_description
          FROM test_requests
         WHERE id = %s AND is_active = TRUE
    """
    sample_sql = """
        SELECT rs.id, rs.sr_no, rs.sample_name, rs.batch_code, rs.quantity,
               rs.parameters, rs.sample_code, rs.category, rs.tests_to_perform,
               rs.tests_json, rs.status, rs.assigned_analyst_id,
               COALESCE(u.full_name, u.username, ''),
               COALESCE(rs.report_format, 'with_logo'),
               COALESCE(rs.tests_with_logo_json, ''),
               COALESCE(rs.tests_without_logo_json, ''),
               rs.package_id, rs.package_version_no, rs.package_type,
               COALESCE(rs.protocol_no, ''),
               rs.assigned_micro_analyst_id,
               COALESCE(um.full_name, um.username, ''),
               rs.verify_review_date,
               COALESCE(rs.verify_lab_code, ''),
               COALESCE(rs.verify_sample_condition, ''),
               rs.verify_qty_checked,
               rs.verify_chemical_available,
               rs.verify_methods_available,
               rs.verify_methods_informed,
               rs.verify_tat_informed,
               rs.verify_ready_to_issue,
               rs.verify_conformity_statement
          FROM request_samples rs
          LEFT JOIN users u ON u.id = rs.assigned_analyst_id
          LEFT JOIN users um ON um.id = rs.assigned_micro_analyst_id
         WHERE rs.request_id = %s AND rs.is_active = TRUE
         ORDER BY rs.sr_no
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(header_sql, (request_id,))
            header = cur.fetchone()
            if not header:
                return None
            cur.execute(sample_sql, (request_id,))
            sample_rows = cur.fetchall()

    customer = get_customer_by_id(header[1])
    if customer is None:
        return None

    samples: list[SampleRow] = []
    for row in sample_rows:
        keys: list[str] = []
        if row[9]:
            try:
                parsed = json.loads(row[9])
                if isinstance(parsed, list):
                    keys = [str(k) for k in parsed]
            except json.JSONDecodeError:
                keys = []
        logo_keys: list[str] = []
        if row[14]:
            try:
                parsed_logo = json.loads(row[14])
                if isinstance(parsed_logo, list):
                    logo_keys = [str(k) for k in parsed_logo]
            except json.JSONDecodeError:
                logo_keys = []
        nwl_keys: list[str] = []
        if row[15]:
            try:
                parsed_nwl = json.loads(row[15])
                if isinstance(parsed_nwl, list):
                    nwl_keys = [str(k) for k in parsed_nwl]
            except json.JSONDecodeError:
                nwl_keys = []
        samples.append(
            SampleRow(
                id=row[0],
                sr_no=row[1],
                sample_name=row[2] or "",
                batch_code=row[3] or "",
                quantity=row[4] or "",
                parameters=row[5] or "",
                sample_code=row[6] or "",
                category=row[7] or "food",
                test_keys=keys,
                status=row[10] or "pending",
                assigned_analyst_id=row[11],
                assigned_analyst_name=row[12] or "",
                report_format=row[13] or REPORT_FORMAT_WITH_LOGO,
                tests_with_logo=logo_keys,
                tests_without_logo=nwl_keys,
                package_id=row[16],
                package_version_no=row[17],
                package_type=row[18],
                protocol_no=row[19] or "",
                assigned_micro_analyst_id=row[20],
                assigned_micro_analyst_name=row[21] or "",
                verify_review_date=row[22],
                verify_lab_code=row[23] or "",
                verify_sample_condition=row[24] or "",
                verify_qty_checked=row[25],
                verify_chemical_available=row[26],
                verify_methods_available=row[27],
                verify_methods_informed=row[28],
                verify_tat_informed=row[29],
                verify_ready_to_issue=row[30],
                verify_conformity_statement=row[31],
            )
        )

    return TestRequestData(
        customer=customer,
        request_date=header[2],
        lab_code=header[3] or "",
        number_of_samples=header[4],
        sampling_by_lab=header[5],
        storage_temperature=header[6] or "",
        test_method_spec=header[7] or "",
        decision_rule=header[8],
        service_type=header[9] or "",
        delivery_mode=header[10] or "",
        payment_details=header[11] or "",
        sample_description=header[12] or "",
        samples=samples,
        request_id=header[0],
    )


def search_test_requests(query: str, limit: int = 20) -> list[RequestSummary]:
    """Search requests by lab code, sample code, or customer name."""
    q = (query or "").strip()
    if not q:
        return []

    pattern = f"%{q}%"
    sql = """
        SELECT tr.id,
               COALESCE(tr.lab_code, ''),
               tr.request_date,
               COALESCE(c.customer_name, ''),
               COUNT(s.id) AS sample_count,
               COALESCE(
                   string_agg(s.sample_code, ', ' ORDER BY s.sr_no),
                   ''
               ) AS sample_codes
          FROM test_requests tr
          JOIN customers c ON c.id = tr.customer_id AND c.is_active = TRUE
          LEFT JOIN request_samples s
            ON s.request_id = tr.id AND s.is_active = TRUE
         WHERE tr.is_active = TRUE
           AND (tr.lab_code ILIKE %s
            OR c.customer_name ILIKE %s
            OR s.sample_code ILIKE %s
            OR s.sample_name ILIKE %s)
         GROUP BY tr.id, tr.lab_code, tr.request_date, c.customer_name
         ORDER BY tr.id DESC
         LIMIT %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pattern, pattern, pattern, pattern, limit))
            rows = cur.fetchall()

    return [
        RequestSummary(
            request_id=r[0],
            lab_code=r[1] or "",
            request_date=r[2],
            customer_name=r[3] or "",
            sample_count=int(r[4] or 0),
            sample_codes=r[5] or "",
        )
        for r in rows
    ]


def update_test_request(
    data: TestRequestData,
    edit_reason: str,
    actor=None,
) -> TestRequestData:
    """
    Update an existing test request and its samples.

    Archives a version snapshot before applying changes.
    """
    if data.request_id is None:
        raise ValueError("Request ID is required to update a test request.")

    validate_edit_reason(edit_reason)
    existing = get_test_request(data.request_id)
    if existing is None:
        raise ValueError(f"Test request #{data.request_id} was not found.")

    save_version(
        "test_requests",
        data.request_id,
        request_snapshot(data.request_id),
        edit_reason,
        actor=actor,
    )

    saved_customer = upsert_customer(
        data.customer,
        edit_reason=edit_reason,
        actor=actor,
    )
    data.customer = saved_customer

    existing_by_id = {s.id: s for s in existing.samples if s.id is not None}
    submitted = [s for s in data.samples if not s.is_empty()]
    submitted_ids = {s.id for s in submitted if s.id is not None}
    assign_derived_sample_codes(data, existing)

    update_request_sql = """
        UPDATE test_requests SET
            customer_id = %s,
            request_date = %s,
            lab_code = %s,
            number_of_samples = %s,
            sampling_by_lab = %s,
            storage_temperature = %s,
            test_method_spec = %s,
            decision_rule = %s,
            service_type = %s,
            delivery_mode = %s,
            payment_details = %s,
            sample_description = %s
         WHERE id = %s
    """
    request_values = (
        saved_customer.id,
        data.request_date,
        (data.lab_code or "").strip(),
        data.number_of_samples,
        data.sampling_by_lab,
        (data.storage_temperature or "").strip() or None,
        (data.test_method_spec or "").strip() or None,
        data.decision_rule,
        (data.service_type or "").strip() or None,
        (data.delivery_mode or "").strip() or None,
        (data.payment_details or "").strip() or None,
        (data.sample_description or "").strip() or None,
        data.request_id,
    )

    update_sample_sql = """
        UPDATE request_samples SET
            sr_no = %s,
            sample_name = %s,
            batch_code = %s,
            quantity = %s,
            parameters = %s,
            sample_code = %s,
            category = %s,
            tests_to_perform = %s,
            tests_json = %s,
            assigned_analyst_id = %s,
            assigned_micro_analyst_id = %s,
            protocol_no = %s,
            report_format = %s,
            tests_with_logo_json = %s,
            tests_without_logo_json = %s,
            package_id = %s,
            package_version_no = %s,
            package_type = %s,
            verify_review_date = %s,
            verify_lab_code = %s,
            verify_sample_condition = %s,
            verify_qty_checked = %s,
            verify_chemical_available = %s,
            verify_methods_available = %s,
            verify_methods_informed = %s,
            verify_tat_informed = %s,
            verify_ready_to_issue = %s,
            verify_conformity_statement = %s,
            updated_at = NOW()
         WHERE id = %s
    """
    insert_sample_sql = """
        INSERT INTO request_samples (
            request_id, sr_no, sample_name, batch_code, quantity, parameters,
            sample_code, category, tests_to_perform, tests_json, status,
            assigned_analyst_id, assigned_micro_analyst_id, protocol_no,
            report_format, tests_with_logo_json,
            tests_without_logo_json, package_id, package_version_no, package_type,
            verify_review_date, verify_lab_code, verify_sample_condition,
            verify_qty_checked, verify_chemical_available, verify_methods_available,
            verify_methods_informed, verify_tat_informed, verify_ready_to_issue,
            verify_conformity_statement,
            expires_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            NOW() + INTERVAL '10 days'
        )
        RETURNING id, sample_code
    """

    saved_samples: list[SampleRow] = []
    analyst_names = {
        u.id: analyst_full_name(u) for u in list_active_analysts()
    }

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(update_request_sql, request_values)

            for old in existing.samples:
                if old.id is not None and old.id not in submitted_ids:
                    if old.status != "pending":
                        raise ValueError(
                            f"Cannot remove sample '{old.sample_code}' "
                            f"because status is '{old.status}'."
                        )
                    cur.execute(
                        "DELETE FROM request_samples WHERE id = %s",
                        (old.id,),
                    )

            for sample in submitted:
                assert_valid_analyst_assignee(sample.assigned_analyst_id)
                category = normalize_category(sample.category)
                if category == CATEGORY_WATER:
                    assert_valid_analyst_assignee(sample.assigned_micro_analyst_id)
                    if (
                        sample.assigned_analyst_id
                        and sample.assigned_micro_analyst_id
                        and sample.assigned_analyst_id
                        == sample.assigned_micro_analyst_id
                    ):
                        raise ValueError(
                            f"Sample Sr. {sample.sr_no}: chemical and micro "
                            "analyst must be different users."
                        )
                (
                    keys,
                    parameters_display,
                    tests_to_perform,
                    pkg_id,
                    pkg_ver,
                    pkg_type,
                ) = _resolve_sample_tests(sample, category)
                tests_json = json.dumps(keys) if keys else None

                if sample.id is not None:
                    old = existing_by_id.get(sample.id)
                    if old is None:
                        raise ValueError(
                            f"Sample id {sample.id} does not belong to this request."
                        )
                    new_code = normalize_sample_code(sample.sample_code)
                    if not new_code:
                        raise ValueError(
                            f"Sample Sr. {sample.sr_no}: sample code is required."
                        )
                    if old.status != "pending" and new_code != normalize_sample_code(
                        old.sample_code
                    ):
                        raise ValueError(
                            f"Cannot change sample code '{old.sample_code}' "
                            f"because status is '{old.status}'."
                        )
                    if (
                        old.status != "pending"
                        and sample.assigned_analyst_id != old.assigned_analyst_id
                    ):
                        raise ValueError(
                            f"Cannot reassign analyst for sample '{old.sample_code}' "
                            f"because status is '{old.status}'."
                        )
                    if (
                        old.status != "pending"
                        and sample.assigned_micro_analyst_id
                        != old.assigned_micro_analyst_id
                    ):
                        raise ValueError(
                            f"Cannot reassign micro analyst for sample "
                            f"'{old.sample_code}' because status is '{old.status}'."
                        )
                    if old.status != "pending" and (
                        (sample.protocol_no or "").strip()
                        != (old.protocol_no or "").strip()
                    ):
                        raise ValueError(
                            f"Cannot change protocol number for sample '{old.sample_code}' "
                            f"because status is '{old.status}'."
                        )
                    if old.status != "pending":
                        sample.protocol_no = old.protocol_no or ""
                    new_fmt = normalize_report_format(sample.report_format)
                    old_fmt = normalize_report_format(old.report_format)
                    if old.status != "pending" and (
                        new_fmt != old_fmt
                        or sample.tests_with_logo != old.tests_with_logo
                        or sample.tests_without_logo != old.tests_without_logo
                    ):
                        raise ValueError(
                            f"Cannot change report format for sample '{old.sample_code}' "
                            f"because status is '{old.status}'."
                        )
                    if new_code != normalize_sample_code(old.sample_code):
                        allocate_sample_code(
                            cur,
                            sample.sample_code,
                            exclude_sample_id=sample.id,
                        )
                    cur.execute(
                        update_sample_sql,
                        (
                            sample.sr_no,
                            (sample.sample_name or "").strip() or None,
                            (sample.batch_code or "").strip() or None,
                            (sample.quantity or "").strip() or None,
                            parameters_display or None,
                            new_code,
                            category,
                            tests_to_perform or None,
                            tests_json,
                            sample.assigned_analyst_id,
                            sample.assigned_micro_analyst_id,
                            (sample.protocol_no or "").strip() or None,
                            new_fmt,
                            _tests_with_logo_json_for_save(sample),
                            _tests_without_logo_json_for_save(sample),
                            pkg_id,
                            pkg_ver,
                            pkg_type,
                            *_verification_tuple(sample),
                            sample.id,
                        ),
                    )
                    sample.sample_code = new_code or old.sample_code
                    sample.category = category
                    sample.parameters = parameters_display or ""
                    sample.test_keys = keys
                    sample.package_id = pkg_id
                    sample.package_version_no = pkg_ver
                    sample.package_type = pkg_type
                    sample.status = old.status
                    sample.assigned_analyst_name = analyst_names.get(
                        sample.assigned_analyst_id, ""
                    ) or old.assigned_analyst_name
                    sample.assigned_micro_analyst_name = analyst_names.get(
                        sample.assigned_micro_analyst_id, ""
                    ) or getattr(old, "assigned_micro_analyst_name", "")
                    saved_samples.append(sample)
                else:
                    code = allocate_sample_code(cur, sample.sample_code)
                    cur.execute(
                        insert_sample_sql,
                        (
                            data.request_id,
                            sample.sr_no,
                            (sample.sample_name or "").strip() or None,
                            (sample.batch_code or "").strip() or None,
                            (sample.quantity or "").strip() or None,
                            parameters_display or None,
                            code,
                            category,
                            tests_to_perform or None,
                            tests_json,
                            sample.assigned_analyst_id,
                            sample.assigned_micro_analyst_id,
                            (sample.protocol_no or "").strip() or None,
                            normalize_report_format(sample.report_format),
                            _tests_with_logo_json_for_save(sample),
                            _tests_without_logo_json_for_save(sample),
                            pkg_id,
                            pkg_ver,
                            pkg_type,
                            *_verification_tuple(sample),
                        ),
                    )
                    new_id, returned_code = cur.fetchone()
                    sample.id = new_id
                    sample.sample_code = returned_code
                    sample.category = category
                    sample.parameters = parameters_display or ""
                    sample.test_keys = keys
                    sample.package_id = pkg_id
                    sample.package_version_no = pkg_ver
                    sample.package_type = pkg_type
                    sample.status = "pending"
                    sample.assigned_analyst_name = analyst_names.get(
                        sample.assigned_analyst_id, ""
                    )
                    sample.assigned_micro_analyst_name = analyst_names.get(
                        sample.assigned_micro_analyst_id, ""
                    )
                    saved_samples.append(sample)

    data.samples = saved_samples
    _sync_reception_protocol_headers(saved_samples, actor, data.request_date)
    codes = ", ".join(s.sample_code for s in saved_samples if s.sample_code)
    log_from_user(
        actor,
        "request.update",
        "test_requests",
        data.request_id,
        details=f"samples={len(saved_samples)}" + (f" [{codes}]" if codes else ""),
        edit_reason=edit_reason,
    )
    return data


def validate_request(data: TestRequestData) -> list[str]:
    """
    Lightweight validation before save / PDF generation.

    Returns
    -------
    list[str]
        Human-readable error messages (empty list means OK).
    """
    errors: list[str] = []
    c = data.customer

    if not (c.customer_name or "").strip():
        errors.append("Customer details (name) are required.")
    if not (c.gst_number or "").strip():
        errors.append("GST number is required (used as permanent customer key).")
    if not (c.contact_person or "").strip():
        errors.append("Name of contact person is required (Contact 1).")
    if not (c.contact_number or "").strip():
        errors.append("Contact number is required.")
    if not (c.email or "").strip():
        errors.append("Email ID is required (Contact 1).")

    contacts = c.resolved_contacts()
    if len(contacts) > 5:
        errors.append("At most 5 contact persons are allowed.")
    for i, contact in enumerate(contacts, start=1):
        has_name = bool((contact.contact_name or "").strip())
        has_email = bool((contact.email or "").strip())
        if has_name and not has_email:
            errors.append(f"Contact {i}: email is required when name is provided.")
        if has_email and not has_name:
            errors.append(f"Contact {i}: name is required when email is provided.")

    if data.request_date is None:
        errors.append("Date is required.")
    if not (data.lab_code or "").strip():
        errors.append("Lab code is required.")

    filled = [s for s in data.samples if not s.is_empty()]
    if not filled:
        errors.append("Add at least one sample row (name + tests to perform).")
    else:
        assign_derived_sample_codes(data)
        seen_codes: set[str] = set()
        for s in filled:
            if not (s.sample_name or "").strip():
                errors.append(f"Sample Sr. {s.sr_no}: name of sample is required.")
            derived_code = normalize_sample_code(s.sample_code)
            if not derived_code:
                errors.append(
                    f"Sample Sr. {s.sr_no}: could not derive sample code from lab code."
                )
            elif not is_valid_sample_code_format(derived_code):
                errors.append(
                    f"Sample Sr. {s.sr_no}: sample code '{derived_code}' "
                    "is invalid (3–32 letters, numbers, dashes, underscores, slashes)."
                )
            elif derived_code in seen_codes:
                errors.append(
                    f"Sample Sr. {s.sr_no}: duplicate sample code '{derived_code}'."
                )
            else:
                seen_codes.add(derived_code)
            if not s.assigned_analyst_id:
                errors.append(f"Sample Sr. {s.sr_no}: assign a chemical analyst.")
            category = normalize_category(s.category)
            if category == CATEGORY_WATER:
                if not s.assigned_micro_analyst_id:
                    errors.append(f"Sample Sr. {s.sr_no}: assign a micro analyst.")
                elif (
                    s.assigned_analyst_id
                    and s.assigned_micro_analyst_id
                    and s.assigned_analyst_id == s.assigned_micro_analyst_id
                ):
                    errors.append(
                        f"Sample Sr. {s.sr_no}: chemical and micro analyst "
                        "must be different users."
                    )
            if not (s.protocol_no or "").strip():
                errors.append(f"Sample Sr. {s.sr_no}: protocol number is required.")
            if s.verify_review_date is None:
                errors.append(
                    f"Sample Sr. {s.sr_no}: verification review date is required."
                )
            if not (s.verify_lab_code or "").strip():
                errors.append(
                    f"Sample Sr. {s.sr_no}: verification lab code is required."
                )
            if not (s.verify_sample_condition or "").strip():
                errors.append(
                    f"Sample Sr. {s.sr_no}: sample condition is required."
                )
            for field, label in (
                (s.verify_qty_checked, "Checked for Sample Quantity"),
                (s.verify_chemical_available, "Checked for Availability of Chemical"),
                (s.verify_methods_available, "Checked for Availability of Methods"),
                (s.verify_methods_informed, "Informed testing Methods to Customer"),
                (s.verify_tat_informed, "Informed turnaround time to Customer"),
                (s.verify_ready_to_issue, "Sample is ready to issue"),
                (s.verify_conformity_statement, "About statement of conformity"),
            ):
                if field is None:
                    errors.append(
                        f"Sample Sr. {s.sr_no}: verification '{label}' is required."
                    )
            if category == CATEGORY_FOOD:
                if not (s.sample_name or "").strip():
                    pass  # name error handled above
                else:
                    from services.test_packages import (
                        describe_sample_package,
                        is_other_parameters_label,
                        parameters_label_to_package_type,
                    )

                    params_label = (s.parameters or "").strip()
                    if is_other_parameters_label(params_label):
                        errors.append(
                            f"Sample Sr. {s.sr_no}: enter custom Parameters text for Other."
                        )
                    elif not params_label:
                        errors.append(
                            f"Sample Sr. {s.sr_no}: select a package type in Parameters "
                            "(FSSAI, Basic Nutrition, Detailed Nutrition, or Other)."
                        )
                    else:
                        ptype = parameters_label_to_package_type(
                            params_label
                        ) or normalize_package_type(s.package_type)
                        if ptype is None:
                            if not params_label:
                                errors.append(
                                    f"Sample Sr. {s.sr_no}: enter custom Parameters text."
                                )
                        else:
                            desc = describe_sample_package(
                                s.sample_name,
                                ptype,
                                category=category,
                            )
                            status = desc.get("status")
                            if status == "inactive":
                                errors.append(
                                    f"Sample Sr. {s.sr_no}: test package for "
                                    f"'{s.sample_name.strip()}' ({package_type_label(ptype)}) "
                                    "exists but is deactivated. Activate it under Test packages."
                                )
                            elif status != "defined":
                                errors.append(
                                    f"Sample Sr. {s.sr_no}: no active test package found for "
                                    f"'{s.sample_name.strip()}' ({package_type_label(ptype)}). "
                                    "Create it under Test packages first."
                                )
                            else:
                                resolved = resolve_package_tests(
                                    s.sample_name,
                                    ptype,
                                    category=category,
                                )
                                wl = filter_keys_for_category(
                                    list(s.tests_with_logo or []), category
                                )
                                nwl = filter_keys_for_category(
                                    list(s.tests_without_logo or []), category
                                )
                                allowed = (
                                    list(resolved.test_keys) if resolved else []
                                )
                                errors.extend(
                                    _validate_intake_tests_in_package(
                                        s.sr_no, wl + nwl, allowed
                                    )
                                )
                                errors.extend(
                                    _validate_report_format_for_package(
                                        s.sr_no, s.report_format, wl, nwl
                                    )
                                )
            else:
                available = tests_for_category(category)
                keys = filter_keys_for_category(list(s.test_keys or []), category)
                if not keys and not (s.parameters or "").strip():
                    if not available:
                        errors.append(
                            f"Sample Sr. {s.sr_no}: no catalog tests are defined yet "
                            f"for category '{category}'."
                        )
                    else:
                        errors.append(
                            f"Sample Sr. {s.sr_no}: assign catalog tests for "
                            f"category '{category}'."
                        )
                errors.extend(
                    _validate_report_format_for_package(
                        s.sr_no,
                        s.report_format,
                        keys if normalize_report_format(s.report_format)
                        != REPORT_FORMAT_WITHOUT_LOGO
                        else [],
                        keys
                        if normalize_report_format(s.report_format)
                        != REPORT_FORMAT_WITH_LOGO
                        else [],
                    )
                )

    return errors


def validation_warnings(data: TestRequestData) -> list[str]:
    """Non-blocking warnings (e.g. mixed Jaggery + Basic Nutrition on one sample)."""
    warnings: list[str] = []
    for s in data.samples:
        if s.is_empty():
            continue
        if normalize_category(s.category) != CATEGORY_FOOD:
            continue
        keys = filter_keys_for_category(list(s.test_keys or []), s.category)
        if has_mixed_food_families(keys):
            warnings.append(
                f"Sample Sr. {s.sr_no}: Jaggery and Basic Nutrition tests use "
                "different protocol templates — prefer one protocol per sample."
            )
    return warnings
