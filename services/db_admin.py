"""
services/db_admin.py
--------------------
Admin database explorer: list tables, browse rows, activate/deactivate rows.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.versions import save_version, validate_edit_reason

# Tables that must never be toggled from the explorer.
READ_ONLY_TABLES = frozenset(
    {
        "audit_log",
        "entity_versions",
        "user_roles",
        "sample_test_package_tests",
        "custom_formula_inputs",
    }
)

SENSITIVE_COLUMNS = frozenset({"password_hash"})

# Partial-unique business keys used when activating a row.
# sample_test_packages uses composite key — handled specially in conflict helpers.
_CONFLICT_KEYS: dict[str, list[str]] = {
    "customers": ["gst_number"],
    "custom_formulas": ["test_key"],
    "request_samples": ["sample_code"],
    "sample_test_packages": ["__composite__"],
}

# Searchable text columns per table (optional filter).
_SEARCH_COLUMNS: dict[str, list[str]] = {
    "customers": ["customer_name", "gst_number"],
    "users": ["username", "full_name"],
    "custom_formulas": ["name", "test_key"],
    "request_samples": ["sample_code", "sample_name"],
    "sample_test_packages": ["sample_product_name"],
    "test_requests": ["lab_code"],
}

_TABLE_GROUPS: dict[str, str] = {
    "customers": "Business",
    "customer_contacts": "Business",
    "test_requests": "Business",
    "request_samples": "Business",
    "sample_protocols": "Business",
    "sample_test_results": "Business",
    "sample_test_packages": "Business",
    "sample_test_package_tests": "Business",
    "custom_formulas": "Business",
    "custom_formula_inputs": "Business",
    "users": "Auth",
    "user_roles": "Auth",
    "audit_log": "Audit",
    "entity_versions": "Audit",
}

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _safe_identifier(name: str) -> str:
    """Validate SQL identifier (table/column) against injection."""
    key = (name or "").strip().lower()
    if not _IDENTIFIER_RE.match(key):
        raise ValueError(f"Invalid identifier: {name!r}")
    return key


def _snapshot_builder(table: str) -> Optional[Callable[[int], dict[str, Any]]]:
    if table == "customers":
        from services.versions import customer_snapshot

        return customer_snapshot
    if table == "test_requests":
        from services.versions import request_snapshot

        return lambda rid: request_snapshot(rid)
    if table == "sample_test_packages":
        from services.test_packages import package_snapshot

        return package_snapshot
    if table == "custom_formulas":
        from services.custom_formulas import formula_snapshot

        return formula_snapshot
    return None


def list_tables() -> list[dict[str, Any]]:
    """Return public schema tables with registry metadata."""
    sql = """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_type = 'BASE TABLE'
         ORDER BY table_name
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = [r[0] for r in cur.fetchall()]

    result: list[dict[str, Any]] = []
    for name in rows:
        cols = get_table_columns(name)
        has_active = any(c["name"] == "is_active" for c in cols)
        result.append(
            {
                "name": name,
                "group": _TABLE_GROUPS.get(name, "Other"),
                "toggle": name not in READ_ONLY_TABLES and has_active,
                "has_is_active": has_active,
                "pk": _primary_key_column(name),
            }
        )
    return result


def _primary_key_column(table: str) -> str:
    table = _safe_identifier(table)
    sql = """
        SELECT a.attname
          FROM pg_index i
          JOIN pg_attribute a
            ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
         WHERE i.indrelid = %s::regclass
           AND i.indisprimary
         LIMIT 1
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table,))
            row = cur.fetchone()
    if not row:
        return "id"
    return str(row[0])


def get_table_columns(table: str) -> list[dict[str, str]]:
    """Column names and data types for a table."""
    table = _safe_identifier(table)
    sql = """
        SELECT column_name, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
         ORDER BY ordinal_position
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table,))
            rows = cur.fetchall()
    return [{"name": r[0], "type": r[1]} for r in rows]


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, memoryview):
        return bytes(value).decode("utf-8", errors="replace")
    return value


def _mask_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    masked = dict(row)
    if table == "users" and "password_hash" in masked:
        masked["password_hash"] = "********"
    for col in SENSITIVE_COLUMNS:
        if col in masked and masked[col] not in (None, "********"):
            masked[col] = "********"
    return masked


def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return {
        col: _serialize_value(val)
        for col, val in zip(columns, row, strict=False)
    }


def count_rows(
    table: str,
    *,
    include_inactive: bool = True,
    search: Optional[str] = None,
) -> int:
    table = _safe_identifier(table)
    clauses: list[str] = []
    params: list[Any] = []

    cols = [c["name"] for c in get_table_columns(table)]
    if "is_active" in cols and not include_inactive:
        clauses.append("is_active = TRUE")

    q = (search or "").strip()
    if q and table in _SEARCH_COLUMNS:
        or_parts = []
        for col in _SEARCH_COLUMNS[table]:
            if col in cols:
                or_parts.append(f"CAST({col} AS TEXT) ILIKE %s")
                params.append(f"%{q}%")
        if or_parts:
            clauses.append("(" + " OR ".join(or_parts) + ")")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT COUNT(*) FROM {table} {where}"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    return int(row[0]) if row else 0


def fetch_rows(
    table: str,
    *,
    limit: int = 50,
    offset: int = 0,
    include_inactive: bool = True,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Paginated rows from a table (masked for sensitive columns)."""
    table = _safe_identifier(table)
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))

    columns = [c["name"] for c in get_table_columns(table)]
    if not columns:
        return []

    clauses: list[str] = []
    params: list[Any] = []

    if "is_active" in columns and not include_inactive:
        clauses.append("is_active = TRUE")

    q = (search or "").strip()
    if q and table in _SEARCH_COLUMNS:
        or_parts = []
        for col in _SEARCH_COLUMNS[table]:
            if col in columns:
                or_parts.append(f"CAST({col} AS TEXT) ILIKE %s")
                params.append(f"%{q}%")
        if or_parts:
            clauses.append("(" + " OR ".join(or_parts) + ")")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    pk = _primary_key_column(table)
    col_list = ", ".join(columns)
    sql = f"""
        SELECT {col_list}
          FROM {table}
         {where}
         ORDER BY {pk} DESC
         LIMIT %s OFFSET %s
    """
    params.extend([lim, off])

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    return [_mask_row(table, _row_to_dict(columns, r)) for r in rows]


def get_row(table: str, pk_value: Any) -> Optional[dict[str, Any]]:
    """Fetch one row by primary key."""
    table = _safe_identifier(table)
    pk = _primary_key_column(table)
    columns = [c["name"] for c in get_table_columns(table)]
    if not columns:
        return None
    col_list = ", ".join(columns)
    sql = f"SELECT {col_list} FROM {table} WHERE {pk} = %s"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pk_value,))
            row = cur.fetchone()
    if not row:
        return None
    return _mask_row(table, _row_to_dict(columns, row))


def _deactivate_conflicting_rows(
    table: str,
    row: dict[str, Any],
    *,
    exclude_pk: Any,
    actor=None,
) -> list[int]:
    """Deactivate other active rows that share the same business key."""
    keys = _CONFLICT_KEYS.get(table, [])
    if not keys:
        return []

    pk = _primary_key_column(table)
    deactivated: list[int] = []
    if table == "sample_test_packages":
        sql = f"""
            UPDATE {table}
               SET is_active = FALSE, updated_at = NOW()
             WHERE is_active = TRUE
               AND {pk} <> %s
               AND lower(trim(sample_product_name)) = lower(trim(%s))
               AND package_type = %s
               AND category = %s
            RETURNING {pk}
        """
        params = (
            exclude_pk,
            row.get("sample_product_name"),
            row.get("package_type"),
            row.get("category"),
        )
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                for r in cur.fetchall():
                    deactivated.append(int(r[0]))
    else:
        for key in keys:
            if key == "__composite__":
                continue
            if key not in row or row.get(key) in (None, ""):
                continue
            extra_set = ""
            if "updated_at" in [c["name"] for c in get_table_columns(table)]:
                extra_set = ", updated_at = NOW()"
            sql = f"""
                UPDATE {table}
                   SET is_active = FALSE{extra_set}
                 WHERE is_active = TRUE
                   AND {pk} <> %s
                   AND {key} = %s
                RETURNING {pk}
            """
            params = (exclude_pk, row.get(key))
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    for r in cur.fetchall():
                        deactivated.append(int(r[0]))

    for did in deactivated:
        log_from_user(
            actor,
            "db_admin.deactivate_conflict",
            table,
            did,
            details=f"Deactivated conflicting row when activating {exclude_pk}",
        )
    return deactivated


def set_row_active(
    table: str,
    pk_value: Any,
    is_active: bool,
    edit_reason: str,
    *,
    actor=None,
    deactivate_conflicts: bool = False,
) -> dict[str, Any]:
    """
    Activate or deactivate a row (soft delete).

    Delegates to existing service functions where business rules apply.
    """
    table = _safe_identifier(table)
    if table in READ_ONLY_TABLES:
        raise ValueError(f"Table '{table}' is read-only.")

    validate_edit_reason(edit_reason)

    row = get_row(table, pk_value)
    if row is None:
        raise ValueError(f"Row not found in {table} (pk={pk_value}).")

    pk = _primary_key_column(table)
    pk_int = int(pk_value) if str(pk_value).isdigit() else pk_value

    if "is_active" not in row:
        raise ValueError(f"Table '{table}' does not support row activation.")

    current = bool(row.get("is_active"))
    if current == is_active:
        return row

    # Delegate to specialized services.
    if table == "users":
        from services.users import set_active

        set_active(int(pk_int), is_active, actor=actor)
        updated = get_row(table, pk_value)
        return updated or row

    if table == "sample_test_packages":
        from services.test_packages import activate_package, delete_package

        if is_active:
            activate_package(int(pk_int), edit_reason, actor=actor)
        else:
            delete_package(int(pk_int), edit_reason, actor=actor)
        updated = get_row(table, pk_value)
        return updated or row

    if table == "custom_formulas":
        if is_active:
            rec_row = get_row(table, pk_value)
            if rec_row and rec_row.get("is_validated"):
                if deactivate_conflicts:
                    _deactivate_conflicting_rows(
                        table, rec_row, exclude_pk=pk_int, actor=actor
                    )
                builder = _snapshot_builder(table)
                if builder:
                    snap = builder(int(pk_int))
                    if snap:
                        save_version(table, pk_int, snap, edit_reason, actor=actor)
                sql = """
                    UPDATE custom_formulas
                       SET is_active = TRUE, updated_at = NOW()
                     WHERE id = %s
                """
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql, (pk_int,))
                from services.custom_formulas import invalidate_cache

                invalidate_cache()
            else:
                from services.custom_formulas import activate_validated_formula

                activate_validated_formula(int(pk_int), actor=actor)
        else:
            from services.custom_formulas import deactivate_formula

            deactivate_formula(int(pk_int), actor=actor)
        updated = get_row(table, pk_value)
        return updated or row

    # Generic tables.
    builder = _snapshot_builder(table)
    if builder and str(pk_int).isdigit():
        snap = builder(int(pk_int))
        if snap:
            save_version(table, pk_int, snap, edit_reason, actor=actor)

    if is_active and deactivate_conflicts:
        _deactivate_conflicting_rows(table, row, exclude_pk=pk_int, actor=actor)
    elif is_active and table in _CONFLICT_KEYS:
        if table == "sample_test_packages":
            check_sql = """
                SELECT id FROM sample_test_packages
                 WHERE is_active = TRUE AND id <> %s
                   AND lower(trim(sample_product_name)) = lower(trim(%s))
                   AND package_type = %s AND category = %s
                 LIMIT 1
            """
            params = (
                pk_int,
                row.get("sample_product_name"),
                row.get("package_type"),
                row.get("category"),
            )
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(check_sql, params)
                    conflict = cur.fetchone()
            if conflict:
                raise ValueError(
                    f"Cannot activate: another active package exists for this "
                    f"product/type (id={conflict[0]}). Deactivate it first or "
                    "enable 'Deactivate conflicting row'."
                )
        else:
            for key in _CONFLICT_KEYS[table]:
                if key == "__composite__" or key not in row:
                    continue
                check_sql = f"""
                    SELECT {pk} FROM {table}
                     WHERE is_active = TRUE AND {pk} <> %s AND {key} = %s
                     LIMIT 1
                """
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute(check_sql, (pk_int, row.get(key)))
                        conflict = cur.fetchone()
                if conflict:
                    raise ValueError(
                        f"Cannot activate: another active row exists with the same "
                        f"{key} (id={conflict[0]}). Deactivate it first or enable "
                        "'Deactivate conflicting row'."
                    )

    extra = ""
    cols = [c["name"] for c in get_table_columns(table)]
    if "updated_at" in cols:
        extra = ", updated_at = NOW()"

    sql = f"UPDATE {table} SET is_active = %s{extra} WHERE {pk} = %s"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (is_active, pk_int))

    action = "db_admin.activate" if is_active else "db_admin.deactivate"
    log_from_user(
        actor,
        action,
        table,
        str(pk_int),
        edit_reason=edit_reason,
    )

    updated = get_row(table, pk_value)
    return updated or row


def table_label(table: str) -> str:
    """Human-readable table label."""
    return (table or "").replace("_", " ").title()
