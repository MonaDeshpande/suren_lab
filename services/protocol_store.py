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
from services.protocols.test_catalog import TEST_CATALOG, get_test, missing_required_inputs


@dataclass
class ProtocolHeader:
    sample_id: int
    protocol_no: str = ""
    issued_to: str = ""
    issued_by: str = ""
    sample_received_on: Optional[date] = None
    date_of_analysis: Optional[date] = None
    appearance_text: str = ""


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


def upsert_protocol_header(header: ProtocolHeader, actor=None) -> None:
    """Insert or update the 2-row protocol header + appearance for a sample."""
    sql = """
        INSERT INTO sample_protocols (
            sample_id, protocol_no, issued_to, issued_by,
            sample_received_on, date_of_analysis, appearance_text, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (sample_id) DO UPDATE SET
            protocol_no = EXCLUDED.protocol_no,
            issued_to = EXCLUDED.issued_to,
            issued_by = EXCLUDED.issued_by,
            sample_received_on = EXCLUDED.sample_received_on,
            date_of_analysis = EXCLUDED.date_of_analysis,
            appearance_text = EXCLUDED.appearance_text,
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
                    header.date_of_analysis,
                    (header.appearance_text or "").strip() or None,
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
               COALESCE(appearance_text,'')
          FROM sample_protocols
         WHERE sample_id = %s
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
        appearance_text=row[6],
    )


def get_result_context(sample_id: int) -> dict[str, float]:
    """Numeric results already saved for this sample (for dry-basis formulas)."""
    sql = """
        SELECT test_key, result_numeric
          FROM sample_test_results
         WHERE sample_id = %s AND result_numeric IS NOT NULL
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
         WHERE sample_id = %s
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
    missing = missing_required_inputs(test, inputs)
    if missing:
        # Caller shows popup; we still raise with a clear marker
        raise ValueError("MISSING:" + "|".join(missing))

    ctx = get_result_context(sample_id)
    display, numeric = test.calculate(inputs, ctx)

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
                    test.method,
                    test.unit,
                    json.dumps(inputs),
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
        method=test.method,
        unit=test.unit,
        inputs=inputs,
        result_value=display,
        result_numeric=numeric,
    )
