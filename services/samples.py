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

ALLOWED_STATUSES = ("pending", "in_progress", "completed", "reported")

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
            COALESCE(s.category, 'food')
          FROM request_samples s
          JOIN test_requests tr ON tr.id = s.request_id
          JOIN customers c ON c.id = tr.customer_id
"""


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

    def selected_test_keys(self) -> list[str]:
        """Parse catalog keys assigned by reception."""
        import json

        if not (self.tests_json or "").strip():
            return []
        try:
            data = json.loads(self.tests_json)
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


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


def get_by_code(sample_code: str) -> Optional[SampleRecord]:
    """Fetch one non-expired sample by exact sample_code (case-insensitive)."""
    code = (sample_code or "").strip().upper()
    if not code:
        return None

    sql = _SAMPLE_SELECT + """
         WHERE UPPER(s.sample_code) = %s
           AND s.expires_at > NOW()
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (code,))
            row = cur.fetchone()

    return _row_to_record(row) if row else None


def search_open(
    query: str,
    by: str = "sample",
    limit: int = 50,
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
    sql = _SAMPLE_SELECT + "\n         WHERE s.expires_at > NOW()\n"
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

    sql += "         ORDER BY s.created_at DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [_row_to_record(r) for r in rows]


def list_open(limit: int = 50, status: Optional[str] = None) -> list[SampleRecord]:
    """
    List non-expired samples for the analyst queue (newest first).

    Parameters
    ----------
    status : optional filter — pending | in_progress | completed | reported
    """
    sql = _SAMPLE_SELECT + "\n         WHERE s.expires_at > NOW()\n"
    params: list = []
    if status and status in ALLOWED_STATUSES:
        sql += "           AND s.status = %s\n"
        params.append(status)

    sql += "         ORDER BY s.created_at DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [_row_to_record(r) for r in rows]



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
    )
