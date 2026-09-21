"""
services/protocol_store.py
--------------------------
Persist protocol header + per-test results for any sample.

Tests are identified by shared catalog test_key (moisture, …) so the same
worksheet applies no matter what the sample is named.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.input_store import inputs_for_calculation, merge_saved_inputs
from services.number_format import format_final_number
from services.protocols.test_catalog import (
    TEST_CATALOG,
    excess_decimal_inputs,
    get_test,
    missing_required_inputs,
)

PROTOCOL_DISCLAIMER_BULLETS: list[str] = [
    "Sample submitted by the customer in their own container.",
    "Above analysis result is valid only for specific sample as stated above, "
    "without any bias to its source.",
    "We claim no responsibility for changes made in the report after dispatch. "
    "e.g. Use of whitener or eraser.",
    "Sample stored for one Week and test Report for one year from the date received.",
    "Duplicate copies of Report or Invoice will be charged extra.",
]


def default_protocol_disclaimer_text() -> str:
    """Default multi-line protocol disclaimer for Analyst editing."""
    lines = ["Disclaimer:"]
    for index, bullet in enumerate(PROTOCOL_DISCLAIMER_BULLETS, start=1):
        lines.append(f"{index}. {bullet}")
    return "\n".join(lines)


def format_protocol_disclaimer_paragraphs(text: str | None) -> list[str]:
    """Split stored disclaimer into non-empty lines for DOCX rendering."""
    raw = (text or "").strip()
    if not raw:
        raw = default_protocol_disclaimer_text()
    return [line.strip() for line in raw.splitlines() if line.strip()]


@dataclass
class ProtocolHeader:
    sample_id: int
    protocol_no: str = ""
    issued_to: str = ""
    issued_by: str = ""
    sample_received_on: Optional[date] = None
    date_of_analysis: Optional[date] = None
    date_of_analysis_from: Optional[date] = None
    date_of_analysis_to: Optional[date] = None
    appearance_text: str = ""
    protocol_disclaimer_text: str = ""


def _fmt_analysis_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def format_analysis_date_range(
    date_from: Optional[date],
    date_to: Optional[date],
    *,
    legacy_single: Optional[date] = None,
) -> str:
    """Render analysis dates as DD/MM/YYYY or DD/MM/YYYY to DD/MM/YYYY."""
    start = date_from or legacy_single
    end = date_to or legacy_single or start
    if start is None and end is None:
        return ""
    if start is None:
        return _fmt_analysis_date(end)
    if end is None or start == end:
        return _fmt_analysis_date(start)
    return f"{_fmt_analysis_date(start)} to {_fmt_analysis_date(end)}"


def validate_analysis_date_range(
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[str]:
    """Return validation errors when analysis end precedes start."""
    if date_from is None or date_to is None:
        return []
    if date_to < date_from:
        return ["Analysis Date To must be on or after Analysis Date From."]
    return []


@dataclass
class TestResultRow:
    test_key: str
    test_name: str
    method: str
    unit: str
    inputs: dict[str, Any]
    result_value: str
    result_numeric: Optional[float]
    calculated_at: Optional[datetime] = None


def sync_reception_protocol_header(
    sample_id: int,
    *,
    protocol_no: str,
    issued_to: str,
    issued_by: str,
    sample_received_on: Optional[date] = None,
    actor=None,
) -> None:
    """
    Set reception-owned protocol header fields.

    Preserves analyst-entered date_of_analysis and appearance_text when present.
    """
    existing = get_protocol_header(sample_id)
    header = ProtocolHeader(
        sample_id=sample_id,
        protocol_no=protocol_no,
        issued_to=issued_to,
        issued_by=issued_by,
        sample_received_on=(
            sample_received_on
            if sample_received_on is not None
            else (existing.sample_received_on if existing else None)
        ),
        date_of_analysis=existing.date_of_analysis if existing else None,
        date_of_analysis_from=(
            existing.date_of_analysis_from if existing else None
        ),
        date_of_analysis_to=(
            existing.date_of_analysis_to if existing else None
        ),
        appearance_text=(existing.appearance_text if existing else "") or "",
        protocol_disclaimer_text=(
            existing.protocol_disclaimer_text if existing else ""
        ),
    )
    upsert_protocol_header(header, actor=actor)


def upsert_protocol_header(header: ProtocolHeader, actor=None) -> None:
    """Insert or update the 2-row protocol header + appearance for a sample."""
    analysis_from = header.date_of_analysis_from or header.date_of_analysis
    analysis_to = header.date_of_analysis_to or header.date_of_analysis or analysis_from
    legacy_single = analysis_from if analysis_from == analysis_to else header.date_of_analysis
    sql = """
        INSERT INTO sample_protocols (
            sample_id, protocol_no, issued_to, issued_by,
            sample_received_on, date_of_analysis,
            date_of_analysis_from, date_of_analysis_to,
            appearance_text, protocol_disclaimer_text, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (sample_id) DO UPDATE SET
            protocol_no = EXCLUDED.protocol_no,
            issued_to = EXCLUDED.issued_to,
            issued_by = EXCLUDED.issued_by,
            sample_received_on = EXCLUDED.sample_received_on,
            date_of_analysis = EXCLUDED.date_of_analysis,
            date_of_analysis_from = EXCLUDED.date_of_analysis_from,
            date_of_analysis_to = EXCLUDED.date_of_analysis_to,
            appearance_text = EXCLUDED.appearance_text,
            protocol_disclaimer_text = EXCLUDED.protocol_disclaimer_text,
            updated_at = NOW()
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    header.sample_id,
                    (header.protocol_no or "").strip() or None,
                    (header.issued_to or "").strip() or None,
                    (header.issued_by or "").strip() or None,
                    header.sample_received_on,
                    legacy_single or analysis_from,
                    analysis_from,
                    analysis_to,
                    (header.appearance_text or "").strip() or None,
                    (header.protocol_disclaimer_text or "").strip() or None,
                ),
            )
    log_from_user(
        actor,
        "protocol.upsert",
        "sample_protocols",
        header.sample_id,
        details=(header.protocol_no or "").strip() or None,
    )


def get_protocol_header(sample_id: int) -> Optional[ProtocolHeader]:
    sql = """
        SELECT sample_id, COALESCE(protocol_no,''), COALESCE(issued_to,''),
               COALESCE(issued_by,''), sample_received_on, date_of_analysis,
               date_of_analysis_from, date_of_analysis_to,
               COALESCE(appearance_text,''),
               COALESCE(protocol_disclaimer_text,'')
          FROM sample_protocols
         WHERE sample_id = %s AND is_active = TRUE
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (sample_id,))
            row = cur.fetchone()
    if not row:
        return None
    return ProtocolHeader(
        sample_id=row[0],
        protocol_no=row[1],
        issued_to=row[2],
        issued_by=row[3],
        sample_received_on=row[4],
        date_of_analysis=row[5],
        date_of_analysis_from=row[6],
        date_of_analysis_to=row[7],
        appearance_text=row[8],
        protocol_disclaimer_text=row[9] or "",
    )


def get_result_context(sample_id: int) -> dict[str, float]:
    """Numeric results already saved for this sample (for dry-basis formulas)."""
    sql = """
        SELECT test_key, result_numeric
          FROM sample_test_results
         WHERE sample_id = %s AND is_active = TRUE AND result_numeric IS NOT NULL
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (sample_id,))
            rows = cur.fetchall()
    return {r[0]: float(r[1]) for r in rows}


def list_results(sample_id: int) -> list[TestResultRow]:
    sql = """
        SELECT test_key, test_name, COALESCE(method,''), COALESCE(unit,''),
               COALESCE(inputs_json,'{}'), COALESCE(result_value,''),
               result_numeric, calculated_at
          FROM sample_test_results
         WHERE sample_id = %s AND is_active = TRUE
         ORDER BY id
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (sample_id,))
            rows = cur.fetchall()
    out = []
    for r in rows:
        try:
            inputs = json.loads(r[4] or "{}")
        except json.JSONDecodeError:
            inputs = {}
        out.append(
            TestResultRow(
                test_key=r[0],
                test_name=r[1],
                method=r[2],
                unit=r[3],
                inputs=inputs,
                result_value=r[5],
                result_numeric=r[6],
                calculated_at=r[7],
            )
        )
    return out


def save_test_result(
    sample_id: int,
    test_key: str,
    inputs: dict[str, Any],
    actor=None,
) -> TestResultRow:
    """
    Validate inputs, run shared catalog formula, upsert result.

    Raises
    ------
    ValueError
        If required fields are empty or calculation fails.
    """
    if test_key not in TEST_CATALOG:
        raise ValueError(f"Unknown test_key: {test_key}")

    test = get_test(test_key)
    form_inputs = {k: v for k, v in inputs.items() if k != "recalc"}
    missing = missing_required_inputs(test, form_inputs)
    if missing:
        # Caller shows popup; we still raise with a clear marker
        raise ValueError("MISSING:" + "|".join(missing))

    excess = excess_decimal_inputs(test, form_inputs)
    if excess:
        raise ValueError("DECIMALS:" + "|".join(excess))

    existing_inputs: dict[str, Any] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT inputs_json
                  FROM sample_test_results
                 WHERE sample_id = %s AND test_key = %s
                """,
                (sample_id, test_key),
            )
            row = cur.fetchone()
            if row and row[0]:
                try:
                    existing_inputs = json.loads(row[0])
                except json.JSONDecodeError:
                    existing_inputs = {}

    stored_inputs = merge_saved_inputs(existing_inputs, form_inputs)
    calc_inputs = inputs_for_calculation(stored_inputs)

    ctx = get_result_context(sample_id)
    display, numeric = test.calculate(calc_inputs, ctx)
    if numeric is not None:
        display = format_final_number(numeric)

    unit = test.unit or ""
    from services.protocols.test_catalog import MICRO_TEST_KEYS

    if test_key in MICRO_TEST_KEYS:
        spec = None
        try:
            from services.catalog_specs import get_spec

            spec = get_spec(test_key)
        except Exception:  # noqa: BLE001
            spec = None
        entered_unit = str(form_inputs.get("result_unit") or "").strip()
        if entered_unit:
            unit = entered_unit
        elif spec is not None and spec.default_unit:
            unit = spec.default_unit
        entered_method = str(form_inputs.get("method_override") or "").strip()
        if entered_method:
            method_override = entered_method
        elif spec is not None and spec.method_of_analysis:
            method_override = spec.method_of_analysis
        else:
            method_override = test.method
    else:
        method_override = test.method
        try:
            from services.catalog_specs import get_spec

            spec = get_spec(test_key)
            if spec is not None and spec.method_of_analysis:
                method_override = spec.method_of_analysis
        except Exception:  # noqa: BLE001
            pass

    sql = """
        INSERT INTO sample_test_results (
            sample_id, test_key, test_name, method, unit,
            inputs_json, result_value, result_numeric, calculated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (sample_id, test_key) DO UPDATE SET
            test_name = EXCLUDED.test_name,
            method = EXCLUDED.method,
            unit = EXCLUDED.unit,
            inputs_json = EXCLUDED.inputs_json,
            result_value = EXCLUDED.result_value,
            result_numeric = EXCLUDED.result_numeric,
            calculated_at = NOW()
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    sample_id,
                    test.key,
                    test.name,
                    method_override,
                    unit,
                    json.dumps(stored_inputs),
                    display,
                    numeric,
                ),
            )

    log_from_user(
        actor,
        "result.save",
        "sample_test_results",
        sample_id,
        details=f"{test.key}={display}",
    )
    return TestResultRow(
        test_key=test.key,
        test_name=test.name,
        method=method_override,
        unit=unit,
        inputs=stored_inputs,
        result_value=display,
        result_numeric=numeric,
    )
