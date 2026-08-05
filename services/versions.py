"""
services/versions.py
--------------------
Immutable version snapshots before edits + mandatory edit-reason validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from db.connection import get_db
from services.audit import actor_display_name

MIN_EDIT_REASON_LEN = 10


@dataclass
class VersionRow:
    id: int
    entity_table: str
    entity_id: str
    version_no: int
    snapshot_json: str
    edit_reason: str
    user_id: Optional[int]
    user_name: str
    created_at: datetime

    def snapshot(self) -> dict[str, Any]:
        try:
            data = json.loads(self.snapshot_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def validate_edit_reason(reason: str) -> None:
    """Raise ValueError when edit reason is missing or too short."""
    text = (reason or "").strip()
    if not text:
        raise ValueError("Edit reason is required when changing existing data.")
    if len(text) < MIN_EDIT_REASON_LEN:
        raise ValueError(
            f"Edit reason must be at least {MIN_EDIT_REASON_LEN} characters."
        )


def _json_default(obj: Any) -> str:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def snapshot_to_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, default=_json_default, ensure_ascii=False)


def next_version_no(entity_table: str, entity_id: str) -> int:
    sql = """
        SELECT COALESCE(MAX(version_no), 0) + 1
          FROM entity_versions
         WHERE entity_table = %s AND entity_id = %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (entity_table, str(entity_id)))
                row = cur.fetchone()
        return int(row[0]) if row else 1
    except Exception:  # noqa: BLE001
        return 1


def save_version(
    entity_table: str,
    entity_id: str | int,
    snapshot: dict[str, Any],
    edit_reason: str,
    actor=None,
) -> int:
    """
    Archive the prior state before a live-row update.

    Returns the new version row id.
    """
    validate_edit_reason(edit_reason)
    eid = str(entity_id)
    version_no = next_version_no(entity_table, eid)
    uid = getattr(actor, "id", None) if actor is not None else None
    name = actor_display_name(actor)

    sql = """
        INSERT INTO entity_versions (
            entity_table, entity_id, version_no, snapshot_json,
            edit_reason, user_id, user_name
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    entity_table,
                    eid,
                    version_no,
                    snapshot_to_json(snapshot),
                    edit_reason.strip(),
                    uid,
                    name,
                ),
            )
            row = cur.fetchone()
    return int(row[0])


def list_versions(
    entity_table: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 100,
) -> list[VersionRow]:
    lim = max(1, min(int(limit), 500))
    clauses: list[str] = []
    params: list[Any] = []

    if entity_table:
        clauses.append("entity_table = %s")
        params.append(entity_table.strip())
    if entity_id is not None and str(entity_id).strip():
        clauses.append("entity_id = %s")
        params.append(str(entity_id).strip())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT id, entity_table, entity_id, version_no, snapshot_json,
               edit_reason, user_id, user_name, created_at
          FROM entity_versions
         {where}
         ORDER BY created_at DESC
         LIMIT %s
    """
    params.append(lim)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []

    return [_row_to_version(r) for r in rows]


def get_version(version_id: int) -> Optional[VersionRow]:
    sql = """
        SELECT id, entity_table, entity_id, version_no, snapshot_json,
               edit_reason, user_id, user_name, created_at
          FROM entity_versions
         WHERE id = %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (version_id,))
                row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    return _row_to_version(row)


def customer_snapshot(customer_id: int) -> dict[str, Any]:
    """Build JSON snapshot of a customer row + contacts."""
    from services.customers import get_customer_by_id

    customer = get_customer_by_id(customer_id)
    if customer is None:
        return {}
    return {
        "id": customer.id,
        "customer_name": customer.customer_name,
        "address": customer.address,
        "contact_person": customer.contact_person,
        "contact_number": customer.contact_number,
        "email": customer.email,
        "gst_number": customer.gst_number,
        "contacts": [
            {
                "position": c.position,
                "contact_name": c.contact_name,
                "email": c.email,
            }
            for c in customer.contacts
        ],
    }


def request_snapshot(request_id: int) -> dict[str, Any]:
    """Build JSON snapshot of a test request + samples + customer."""
    from services.requests import get_test_request

    data = get_test_request(request_id)
    if data is None:
        return {}

    customer = data.customer
    return {
        "request_id": data.request_id,
        "request_date": data.request_date,
        "lab_code": data.lab_code,
        "number_of_samples": data.number_of_samples,
        "sampling_by_lab": data.sampling_by_lab,
        "storage_temperature": data.storage_temperature,
        "test_method_spec": data.test_method_spec,
        "decision_rule": data.decision_rule,
        "service_type": data.service_type,
        "delivery_mode": data.delivery_mode,
        "payment_details": data.payment_details,
        "sample_description": data.sample_description,
        "customer": customer_snapshot(customer.id) if customer.id else {},
        "samples": [
            {
                "id": getattr(s, "id", None),
                "sr_no": s.sr_no,
                "sample_name": s.sample_name,
                "batch_code": s.batch_code,
                "quantity": s.quantity,
                "parameters": s.parameters,
                "test_keys": list(s.test_keys or []),
                "category": s.category,
                "sample_code": s.sample_code,
                "status": getattr(s, "status", None),
                "package_id": getattr(s, "package_id", None),
                "package_version_no": getattr(s, "package_version_no", None),
                "package_type": getattr(s, "package_type", None),
            }
            for s in data.samples
        ],
    }


def _row_to_version(row: tuple) -> VersionRow:
    return VersionRow(
        id=row[0],
        entity_table=row[1] or "",
        entity_id=row[2] or "",
        version_no=row[3],
        snapshot_json=row[4] or "{}",
        edit_reason=row[5] or "",
        user_id=row[6],
        user_name=row[7] or "",
        created_at=row[8],
    )
