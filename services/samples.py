"""
services/samples.py
-------------------
Analyst-facing sample lookups and status updates.

Samples are keyed by unique sample_code (e.g. SLS-260717-0001).
Only non-expired rows (expires_at > NOW()) are visible — 10-day retention.
Search by lab code, sample code/name, or client name via search_open().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from db.connection import get_db
from services.audit import log_from_user
from services.protocols.test_catalog import (
    CATEGORY_WATER,
    catalog_keys_for_category,
    normalize_category,
)
from services.water_report_catalog import (
    WATER_REPORT_EXCLUDED_KEYS,
    water_report_keys_ordered,
)

import json
import re

ALLOWED_STATUSES = ("pending", "in_progress", "completed", "reported")

REPORT_FORMAT_WITH_LOGO = "with_logo"
REPORT_FORMAT_WITHOUT_LOGO = "without_logo"
REPORT_FORMAT_BOTH = "both"
REPORT_FORMATS = (
    REPORT_FORMAT_WITH_LOGO,
    REPORT_FORMAT_WITHOUT_LOGO,
    REPORT_FORMAT_BOTH,
)

REPORT_FORMAT_LABELS: dict[str, str] = {
    REPORT_FORMAT_WITH_LOGO: "A — With Logo",
    REPORT_FORMAT_WITHOUT_LOGO: "B — Without Logo",
    REPORT_FORMAT_BOTH: "Both",
}

LABEL_TO_REPORT_FORMAT = {v: k for k, v in REPORT_FORMAT_LABELS.items()}

# Analyst find modes for search_open (lab code / sample / client name)
SEARCH_BY = ("lab_code", "sample", "client")

_SAMPLE_SELECT = """
        SELECT
            s.id, s.request_id, s.sample_code, s.sr_no,
            COALESCE(s.sample_name, ''), COALESCE(s.batch_code, ''),
            COALESCE(s.quantity, ''), COALESCE(s.parameters, ''),
            COALESCE(s.tests_to_perform, ''), s.status,
            COALESCE(s.analyst_remarks, ''),
            s.created_at, s.expires_at,
            tr.request_date, COALESCE(tr.lab_code, ''),
            COALESCE(c.customer_name, ''), COALESCE(c.contact_person, ''),
            COALESCE(s.tests_json, ''),
            COALESCE(c.address, ''), COALESCE(c.email, ''),
            COALESCE(c.gst_number, ''), COALESCE(c.contact_number, ''),
            tr.sampling_by_lab,
            COALESCE(s.category, 'food'),
            s.assigned_analyst_id,
            COALESCE(ua.full_name, ua.username, ''),
            COALESCE(s.report_format, 'with_logo'),
            COALESCE(s.tests_with_logo_json, ''),
            COALESCE(s.tests_without_logo_json, ''),
            COALESCE(s.protocol_no, ''),
            COALESCE(s.package_type, ''),
            s.assigned_micro_analyst_id,
            COALESCE(um.full_name, um.username, '')
          FROM request_samples s
          JOIN test_requests tr ON tr.id = s.request_id AND tr.is_active = TRUE
          JOIN customers c ON c.id = tr.customer_id AND c.is_active = TRUE
          LEFT JOIN users ua ON ua.id = s.assigned_analyst_id
          LEFT JOIN users um ON um.id = s.assigned_micro_analyst_id
"""


def sample_scope_for_user(user) -> tuple[Optional[int], bool]:
    """
    Return (assigned_analyst_id filter, scoped) for sample queries.

    Pure analyst users are scoped to their assignments (chemical or micro).
    Admin, reception, and reviewer roles bypass the filter.
    """
    if user is None:
        return None, False
    if user.has_any_role("admin", "reception", "reviewer"):
        return None, False
    if user.has_role("analyst"):
        return user.id, True
    return None, False


@dataclass
class SampleRecord:
    """One sample job visible to reception / analyst."""

    id: int
    request_id: int
    sample_code: str
    sr_no: int
    sample_name: str
    batch_code: str
    quantity: str
    parameters: str
    tests_to_perform: str
    status: str
    analyst_remarks: str
    created_at: Optional[datetime]
    expires_at: Optional[datetime]
    # Joined from request / customer
    request_date: Optional[date] = None
    lab_code: str = ""
    customer_name: str = ""
    contact_person: str = ""
    tests_json: str = ""  # JSON array of catalog keys
    # Extra client / request fields for Test Report PDF
    customer_address: str = ""
    customer_email: str = ""
    customer_gst: str = ""
    contact_number: str = ""
    sampling_by_lab: Optional[bool] = None
    category: str = "food"  # food | water | cattle_feed_fertilizer
    assigned_analyst_id: Optional[int] = None
    assigned_analyst_name: str = ""
    assigned_micro_analyst_id: Optional[int] = None
    assigned_micro_analyst_name: str = ""
    protocol_no: str = ""
    report_format: str = REPORT_FORMAT_WITH_LOGO
    tests_with_logo_json: str = ""
    tests_without_logo_json: str = ""
    package_type: str = ""  # fssai | basic_nutrition | detailed_nutrition (Food packages)

    def selected_test_keys(self) -> list[str]:
        """Parse catalog keys assigned by reception."""
        if not (self.tests_json or "").strip():
            return []
        try:
            data = json.loads(self.tests_json)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def tests_with_logo_keys(self) -> list[str]:
        """Catalog keys marked for with-logo section when format is both."""
        if not (self.tests_with_logo_json or "").strip():
            return []
        try:
            data = json.loads(self.tests_with_logo_json)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


    def tests_without_logo_keys(self) -> list[str]:
        """Catalog keys marked for without-logo section."""
        if not (self.tests_without_logo_json or "").strip():
            return []
        try:
            data = json.loads(self.tests_without_logo_json)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def normalize_report_format(value: str) -> str:
    """Normalize UI/storage value to a known report format key."""
    key = (value or "").strip().lower()
    if key in REPORT_FORMAT_LABELS:
        return key
    if key in LABEL_TO_REPORT_FORMAT:
        return LABEL_TO_REPORT_FORMAT[key]
    return REPORT_FORMAT_WITH_LOGO


def report_format_label(value: str) -> str:
    """Human label for a stored report_format value."""
    return REPORT_FORMAT_LABELS.get(normalize_report_format(value), value)


def default_test_report_no(sample: SampleRecord, *, with_logo: bool) -> str:
    """
    Report No for a final test report.

    Uses sample_code (fallback lab_code). When report_format is Both, appends
    /01 for the with-logo document and /02 for the without-logo document.
    """
    base = (sample.sample_code or sample.lab_code or "").strip().rstrip("/")
    if not base:
        return ""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_BOTH:
        return f"{base}/{'01' if with_logo else '02'}"
    return base


def report_page_label(*, with_logo: bool, page: int = 1, total: int = 1) -> str:
    """Footer page label: 'page n of N' with logo, 'pg n of N' without."""
    word = "page" if with_logo else "pg"
    return f"{word} {page} of {total}"


def default_report_with_logo(sample: SampleRecord) -> bool:
    """True when a single-document report (not Both) should use the logo letterhead."""
    return normalize_report_format(sample.report_format) != REPORT_FORMAT_WITHOUT_LOGO


def water_report_keys(sample: SampleRecord) -> list[str]:
    """Water customer-report keys in IS 10500 section order (excl. calcium_caco3)."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITH_LOGO:
        selected = set(sample.tests_with_logo_keys()) or set(sample.selected_test_keys())
    elif fmt == REPORT_FORMAT_WITHOUT_LOGO:
        selected = set(sample.tests_without_logo_keys()) or set(
            sample.selected_test_keys()
        )
    else:
        selected = set(sample.tests_with_logo_keys()) | set(
            sample.tests_without_logo_keys()
        )
        if not selected:
            selected = set(sample.selected_test_keys())
    selected -= WATER_REPORT_EXCLUDED_KEYS
    return water_report_keys_ordered(selected)


def report_keys_for_sample(sample: SampleRecord) -> list[str]:
    """Catalog keys included on the final test report (food excludes appearance)."""
    cat = normalize_category(sample.category)
    if cat == CATEGORY_WATER:
        return water_report_keys(sample)
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITH_LOGO:
        selected = set(sample.tests_with_logo_keys()) or set(sample.selected_test_keys())
    elif fmt == REPORT_FORMAT_WITHOUT_LOGO:
        selected = set(sample.tests_without_logo_keys()) or set(
            sample.selected_test_keys()
        )
    else:
        selected = set(sample.tests_with_logo_keys()) | set(
            sample.tests_without_logo_keys()
        )
        if not selected:
            selected = set(sample.selected_test_keys())
    ordered = catalog_keys_for_category(cat)
    return [k for k in ordered if k in selected and k != "appearance"]


def logo_test_keys(sample: SampleRecord) -> set[str]:
    """Catalog keys that render in the with-logo final report section."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITHOUT_LOGO:
        return set()
    stored = set(sample.tests_with_logo_keys())
    if stored:
        return stored
    if fmt == REPORT_FORMAT_WITH_LOGO:
        return set(report_keys_for_sample(sample))
    return set()


def no_logo_test_keys(sample: SampleRecord) -> set[str]:
    """Catalog keys that render in the without-logo final report section."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_WITH_LOGO:
        return set()
    stored = set(sample.tests_without_logo_keys())
    if stored:
        return stored
    if fmt == REPORT_FORMAT_WITHOUT_LOGO:
        return set(report_keys_for_sample(sample))
    return set()


def generate_sample_code(cur, on_date: Optional[date] = None) -> str:
    """
    Allocate the next daily sample code: SLS-YYMMDD-NNNN.

    Uses the highest existing code for that day + 1 (inside the caller's transaction).
    """
    day = on_date or date.today()
    prefix = f"SLS-{day.strftime('%y%m%d')}-"
    cur.execute(
        """
        SELECT sample_code
          FROM request_samples
         WHERE sample_code LIKE %s
         ORDER BY sample_code DESC
         LIMIT 1
        """,
        (prefix + "%",),
    )
    row = cur.fetchone()
    if row and row[0]:
        try:
            seq = int(str(row[0]).rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


_SAMPLE_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]{2,31}$")


def normalize_lab_code(code: str) -> str:
    """Uppercase and trim the CTR lab code."""
    return (code or "").strip().upper()


def derive_sample_code(lab_code: str, *, index: int, total: int) -> str:
    """
    Build sample_code from lab code and position among non-empty rows.

    Always append /01, /02, … by enumeration order (index is 1-based).
    E.g. GLG/26/306 → GLG/26/306/01 for the first sample.
    """
    _ = total  # kept for call-site compatibility
    base = normalize_lab_code(lab_code)
    return f"{base}/{index:02d}"


def derive_sample_codes(lab_code: str, count: int) -> list[str]:
    """Return sample codes for count non-empty sample rows."""
    return [
        derive_sample_code(lab_code, index=i, total=count)
        for i in range(1, count + 1)
    ]


def normalize_sample_code(code: str) -> str:
    """Uppercase and trim a user-entered sample code."""
    return (code or "").strip().upper()


def is_valid_sample_code_format(code: str) -> bool:
    """True when code looks like a safe unique sample identifier."""
    normalized = normalize_sample_code(code)
    return bool(normalized and _SAMPLE_CODE_PATTERN.match(normalized))


def sample_code_exists(cur, code: str, exclude_sample_id: int | None = None) -> bool:
    """True when another row already uses this sample_code."""
    normalized = normalize_sample_code(code)
    if not normalized:
        return False
    if exclude_sample_id is not None:
        cur.execute(
            """
            SELECT 1 FROM request_samples
             WHERE UPPER(sample_code) = %s AND id != %s
             LIMIT 1
            """,
            (normalized, exclude_sample_id),
        )
    else:
        cur.execute(
            "SELECT 1 FROM request_samples WHERE UPPER(sample_code) = %s LIMIT 1",
            (normalized,),
        )
    return cur.fetchone() is not None


def allocate_sample_code(
    cur,
    requested: str = "",
    exclude_sample_id: int | None = None,
) -> str:
    """
    Validate and return a sample code (derived from lab code or legacy input).

    Raises ValueError when blank, invalid format, or already taken.
    """
    normalized = normalize_sample_code(requested)
    if not normalized:
        raise ValueError("Sample code is required.")
    if not is_valid_sample_code_format(normalized):
        raise ValueError(
            f"Sample code '{normalized}' is invalid — use 3–32 letters, "
            "numbers, dashes, underscores, or slashes."
        )
    if sample_code_exists(cur, normalized, exclude_sample_id=exclude_sample_id):
        raise ValueError(f"Sample code '{normalized}' is already in use.")
    return normalized


def get_by_code(
    sample_code: str,
    *,
    assigned_analyst_id: Optional[int] = None,
) -> Optional[SampleRecord]:
    """Fetch one non-expired sample by exact sample_code (case-insensitive)."""
    code = (sample_code or "").strip().upper()
    if not code:
        return None

    sql = _SAMPLE_SELECT + """
         WHERE UPPER(s.sample_code) = %s
           AND s.is_active = TRUE
           AND s.expires_at > NOW()
    """
    params: list = [code]
    if assigned_analyst_id is not None:
        sql += (
            "           AND (s.assigned_analyst_id = %s"
            " OR s.assigned_micro_analyst_id = %s)\n"
        )
        params.extend([assigned_analyst_id, assigned_analyst_id])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()

    return _row_to_record(row) if row else None


def search_open(
    query: str,
    by: str = "sample",
    limit: int = 50,
    *,
    assigned_analyst_id: Optional[int] = None,
) -> list[SampleRecord]:
    """
    Find non-expired samples by lab code, sample code/name, or client name.

    Parameters
    ----------
    query : partial text to match (case-insensitive ILIKE)
    by : one of SEARCH_BY — lab_code | sample | client
    limit : max rows returned (newest first)

    Returns
    -------
    list[SampleRecord]
        Empty list if query is blank or by is invalid.
    """
    q = (query or "").strip()
    if not q:
        return []
    if by not in SEARCH_BY:
        raise ValueError(f"Invalid search by '{by}'. Use one of {SEARCH_BY}.")

    pattern = f"%{q}%"
    sql = _SAMPLE_SELECT + "\n         WHERE s.is_active = TRUE AND s.expires_at > NOW()\n"
    params: list = []

    if by == "lab_code":
        sql += "           AND tr.lab_code ILIKE %s\n"
        params.append(pattern)
    elif by == "sample":
        sql += (
            "           AND (s.sample_code ILIKE %s OR s.sample_name ILIKE %s)\n"
        )
        params.extend([pattern, pattern])
    else:  # client
        sql += "           AND c.customer_name ILIKE %s\n"
        params.append(pattern)

    if assigned_analyst_id is not None:
        sql += (
            "           AND (s.assigned_analyst_id = %s"
            " OR s.assigned_micro_analyst_id = %s)\n"
        )
        params.extend([assigned_analyst_id, assigned_analyst_id])

    sql += "         ORDER BY s.created_at DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [_row_to_record(r) for r in rows]


def list_open(
    limit: int = 50,
    status: Optional[str] = None,
    *,
    assigned_analyst_id: Optional[int] = None,
) -> list[SampleRecord]:
    """
    List non-expired samples for the analyst queue (newest first).

    Parameters
    ----------
    status : optional filter — pending | in_progress | completed | reported
    """
    sql = _SAMPLE_SELECT + "\n         WHERE s.is_active = TRUE AND s.expires_at > NOW()\n"
    params: list = []
    if status and status in ALLOWED_STATUSES:
        sql += "           AND s.status = %s\n"
        params.append(status)

    if assigned_analyst_id is not None:
        sql += (
            "           AND (s.assigned_analyst_id = %s"
            " OR s.assigned_micro_analyst_id = %s)\n"
        )
        params.extend([assigned_analyst_id, assigned_analyst_id])

    sql += "         ORDER BY s.created_at DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [_row_to_record(r) for r in rows]


def water_analyst_test_keys(
    sample: SampleRecord,
    user_id: Optional[int],
    *,
    is_admin_like: bool = False,
) -> list[str]:
    """
    Catalog keys an analyst may perform on a water sample.

    Chemical assignee gets WATER_TEST_KEYS; micro assignee gets WATER_MICRO_TEST_KEYS.
    Admin/reception/reviewer (is_admin_like) or dual assignee sees all assigned keys.
    """
    from services.protocols.test_catalog import (
        WATER_MICRO_TEST_KEYS,
        WATER_TEST_KEYS,
    )

    keys = sample.selected_test_keys()
    if is_admin_like or user_id is None:
        return keys
    is_chem = sample.assigned_analyst_id == user_id
    is_micro = sample.assigned_micro_analyst_id == user_id
    if is_chem and is_micro:
        return keys
    allowed: set[str] = set()
    if is_chem:
        allowed.update(WATER_TEST_KEYS)
    if is_micro:
        allowed.update(WATER_MICRO_TEST_KEYS)
    return [k for k in keys if k in allowed]


def worksheet_result_is_saved(row) -> bool:
    """True when a saved worksheet row has a result value or non-empty inputs."""
    if (row.result_value or "").strip():
        return True
    return any(str(v).strip() for v in (row.inputs or {}).values())


def assigned_test_keys_for_sample(
    sample: SampleRecord,
    *,
    role_keys: list[str] | None = None,
) -> list[str]:
    """Catalog keys assigned to the sample, in category order (optional role filter)."""
    cat = normalize_category(sample.category)
    catalog_order = catalog_keys_for_category(cat)
    keys = sample.selected_test_keys()
    if not keys:
        keys = catalog_order

    assigned = [k for k in catalog_order if k in keys]
    extra = [k for k in keys if k not in catalog_order]
    assigned = assigned + extra if keys else list(catalog_order)
    if role_keys is not None:
        allowed = set(role_keys)
        assigned = [k for k in assigned if k in allowed]
    return assigned


def analyst_test_checklist_rows(
    sample: SampleRecord,
    results: list,
    *,
    role_keys: list[str] | None = None,
) -> list[dict]:
    """Rows for the analyst Tests-to-conduct table (Sr, Test, Method, Status, Result)."""
    from services.protocols.test_catalog import get_test

    assigned = assigned_test_keys_for_sample(sample, role_keys=role_keys)
    prior = {r.test_key: r for r in results}
    rows: list[dict] = []
    for idx, key in enumerate(assigned, start=1):
        test = get_test(key)
        saved_row = prior.get(key)
        saved = saved_row is not None and worksheet_result_is_saved(saved_row)
        result_display = "—"
        if saved and saved_row:
            val = (saved_row.result_value or "").strip()
            unit = (saved_row.unit or "").strip()
            if val:
                result_display = f"{val} {unit}".strip()
            else:
                result_display = "Saved"
        rows.append(
            {
                "Sr": idx,
                "Test": test.name,
                "Method": test.method or "—",
                "Status": "Saved" if saved else "Pending",
                "Result": result_display,
            }
        )
    return rows


def update_status(
    sample_code: str,
    status: str,
    analyst_remarks: str = "",
    actor=None,
) -> SampleRecord:
    """
    Update analyst status / remarks for a non-expired sample.

    Raises
    ------
    ValueError
        If status is invalid or sample is missing / expired.
    """
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Use one of {ALLOWED_STATUSES}.")

    code = (sample_code or "").strip().upper()
    sql = """
        UPDATE request_samples
           SET status = %s,
               analyst_remarks = %s,
               updated_at = NOW()
         WHERE UPPER(sample_code) = %s
           AND expires_at > NOW()
     RETURNING id
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, (analyst_remarks or "").strip(), code))
            row = cur.fetchone()

    if not row:
        raise ValueError(
            f"Sample '{sample_code}' not found or has expired (10-day retention)."
        )

    updated = get_by_code(code)
    if updated is None:
        raise RuntimeError("Sample updated but could not be reloaded.")
    log_from_user(
        actor,
        "sample.status",
        "request_samples",
        code,
        details=f"status={status}",
    )
    return updated


def delete_expired_samples(actor=None) -> int:
    """
    Delete sample rows whose expires_at has passed.

    Returns
    -------
    int
        Number of rows deleted.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM request_samples
                 WHERE expires_at <= NOW()
                RETURNING id
                """
            )
            deleted = cur.rowcount

    if deleted:
        log_from_user(
            actor,
            "sample.purge_expired",
            "request_samples",
            details=f"deleted={deleted}",
        )
    return deleted


def _row_to_record(row: tuple) -> SampleRecord:
    return SampleRecord(
        id=row[0],
        request_id=row[1],
        sample_code=row[2],
        sr_no=row[3],
        sample_name=row[4],
        batch_code=row[5],
        quantity=row[6],
        parameters=row[7],
        tests_to_perform=row[8],
        status=row[9],
        analyst_remarks=row[10],
        created_at=row[11],
        expires_at=row[12],
        request_date=row[13],
        lab_code=row[14],
        customer_name=row[15],
        contact_person=row[16],
        tests_json=row[17] if len(row) > 17 else "",
        customer_address=row[18] if len(row) > 18 else "",
        customer_email=row[19] if len(row) > 19 else "",
        customer_gst=row[20] if len(row) > 20 else "",
        contact_number=row[21] if len(row) > 21 else "",
        sampling_by_lab=row[22] if len(row) > 22 else None,
        category=row[23] if len(row) > 23 else "food",
        assigned_analyst_id=row[24] if len(row) > 24 else None,
        assigned_analyst_name=row[25] if len(row) > 25 else "",
        report_format=row[26] if len(row) > 26 else REPORT_FORMAT_WITH_LOGO,
        tests_with_logo_json=row[27] if len(row) > 27 else "",
        tests_without_logo_json=row[28] if len(row) > 28 else "",
        protocol_no=row[29] if len(row) > 29 else "",
        package_type=row[30] if len(row) > 30 else "",
        assigned_micro_analyst_id=row[31] if len(row) > 31 else None,
        assigned_micro_analyst_name=row[32] if len(row) > 32 else "",
    )
