"""
services/catalog_specs.py
-------------------------
DB-backed metadata for built-in catalog tests (method, limits, units).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.protocols.test_catalog import normalize_category
from services.versions import list_versions, save_version, validate_edit_reason

ENTITY_TABLE = "catalog_test_specs"


@dataclass
class CatalogTestSpec:
    test_key: str
    category: str
    test_name: str
    method_of_analysis: str = ""
    limits_text: Optional[str] = None
    limits_desirable: Optional[str] = None
    limits_permissible: Optional[str] = None
    default_unit: str = ""
    unit_editable: bool = False
    sort_order: int = 0
    is_active: bool = True
    current_version_no: int = 1

    @property
    def limits_display(self) -> str:
        """Single-line limits for micro/food reports."""
        if self.limits_text:
            return self.limits_text
        parts: list[str] = []
        if self.limits_desirable:
            parts.append(self.limits_desirable)
        if self.limits_permissible:
            parts.append(self.limits_permissible)
        return " / ".join(parts) if parts else ""

    @property
    def version_label(self) -> str:
        return f"v{self.current_version_no} · Latest"


_spec_cache: dict[str, CatalogTestSpec] = {}
_cache_loaded = False


def clear_spec_cache() -> None:
    global _cache_loaded
    _spec_cache.clear()
    _cache_loaded = False


def _row_to_spec(row: tuple) -> CatalogTestSpec:
    return CatalogTestSpec(
        test_key=row[0],
        category=row[1],
        test_name=row[2],
        method_of_analysis=row[3] or "",
        limits_text=row[4],
        limits_desirable=row[5],
        limits_permissible=row[6],
        default_unit=row[7] or "",
        unit_editable=bool(row[8]),
        sort_order=int(row[9] or 0),
        is_active=bool(row[10]),
        current_version_no=int(row[11] or 1),
    )


_SELECT_COLUMNS = """
    test_key, category, test_name, method_of_analysis,
    limits_text, limits_desirable, limits_permissible,
    default_unit, unit_editable, sort_order, is_active,
    current_version_no
"""


def _load_cache() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    sql = f"""
        SELECT {_SELECT_COLUMNS.strip()}
          FROM catalog_test_specs
         WHERE is_active = TRUE
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        _cache_loaded = True
        return
    _spec_cache.clear()
    for row in rows:
        spec = _row_to_spec(row)
        _spec_cache[spec.test_key] = spec
    _cache_loaded = True


def get_spec(test_key: str) -> Optional[CatalogTestSpec]:
    """Return active catalog spec for a built-in test key (latest version)."""
    key = (test_key or "").strip()
    if not key:
        return None
    _load_cache()
    return _spec_cache.get(key)


def list_specs(category: Optional[str] = None) -> list[CatalogTestSpec]:
    """List active specs, optionally filtered by category."""
    _load_cache()
    specs = list(_spec_cache.values())
    if category:
        cat = normalize_category(category)
        specs = [s for s in specs if s.category == cat]
    return sorted(specs, key=lambda s: (s.category, s.sort_order, s.test_name))


def list_all_specs(category: Optional[str] = None) -> list[CatalogTestSpec]:
    """List all specs including inactive (Admin)."""
    sql = f"""
        SELECT {_SELECT_COLUMNS.strip()}
          FROM catalog_test_specs
    """
    clauses: list[str] = []
    params: list[object] = []
    if category:
        clauses.append("category = %s")
        params.append(normalize_category(category))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY category, sort_order, test_name"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [_row_to_spec(row) for row in rows]


def spec_snapshot(spec: CatalogTestSpec) -> dict[str, Any]:
    """JSON-serializable snapshot for entity_versions."""
    data = asdict(spec)
    data["version_no"] = spec.current_version_no
    return data


def list_spec_versions(test_key: str, *, limit: int = 20):
    """Prior archived versions for one catalog test."""
    return list_versions(ENTITY_TABLE, (test_key or "").strip(), limit=limit)


def update_spec(
    test_key: str,
    *,
    test_name: str,
    method_of_analysis: str,
    limits_text: Optional[str],
    limits_desirable: Optional[str],
    limits_permissible: Optional[str],
    default_unit: str,
    unit_editable: bool,
    sort_order: int,
    edit_reason: str,
    actor=None,
) -> CatalogTestSpec:
    """Save a new catalog spec version (Admin). Archives prior state first."""
    validate_edit_reason(edit_reason)
    key = (test_key or "").strip()
    if not key:
        raise ValueError("test_key is required.")

    existing = get_spec(key)
    if existing is None:
        raise ValueError(f"Catalog spec not found: {key}")

    save_version(
        ENTITY_TABLE,
        key,
        spec_snapshot(existing),
        edit_reason,
        actor=actor,
    )
    new_version = existing.current_version_no + 1

    sql = f"""
        UPDATE catalog_test_specs
           SET test_name = %s,
               method_of_analysis = %s,
               limits_text = %s,
               limits_desirable = %s,
               limits_permissible = %s,
               default_unit = %s,
               unit_editable = %s,
               sort_order = %s,
               current_version_no = %s,
               updated_at = NOW()
         WHERE test_key = %s
           AND is_active = TRUE
        RETURNING {_SELECT_COLUMNS.strip()}
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    (test_name or "").strip(),
                    (method_of_analysis or "").strip(),
                    (limits_text or "").strip() or None,
                    (limits_desirable or "").strip() or None,
                    (limits_permissible or "").strip() or None,
                    (default_unit or "").strip(),
                    bool(unit_editable),
                    int(sort_order),
                    new_version,
                    key,
                ),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"Catalog spec not found: {key}")

    clear_spec_cache()
    log_from_user(
        actor,
        "catalog_spec.update",
        ENTITY_TABLE,
        key,
        details=f"v{new_version}: {edit_reason[:180]}",
    )
    return _row_to_spec(row)


def seed_builtin_specs() -> int:
    """Delegate to db seed (also called from migrate)."""
    from db.seed_catalog_specs import seed_builtin_specs as _seed

    count = _seed()
    clear_spec_cache()
    return count
