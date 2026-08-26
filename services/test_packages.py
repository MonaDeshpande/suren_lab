"""
services/test_packages.py
-------------------------
Versioned test packages keyed by sample product name + package type (Food only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    TEST_CATALOG,
    filter_keys_for_category,
    get_test,
    normalize_category,
    tests_for_category,
)
from services.versions import list_versions, save_version, validate_edit_reason

ENTITY_TABLE = "sample_test_packages"

PACKAGE_TYPE_FSSAI = "fssai"
PACKAGE_TYPE_BASIC_NUTRITION = "basic_nutrition"
PACKAGE_TYPE_DETAILED_NUTRITION = "detailed_nutrition"
# Legacy DB / UI value — treated as Basic Nutrition
PACKAGE_TYPE_NUTRITION_ONLY = "nutrition_only"

PACKAGE_TYPES: dict[str, str] = {
    PACKAGE_TYPE_FSSAI: "FSSAI",
    PACKAGE_TYPE_BASIC_NUTRITION: "Basic Nutrition",
    PACKAGE_TYPE_NUTRITION_ONLY: "Basic Nutrition",
    PACKAGE_TYPE_DETAILED_NUTRITION: "Detailed Nutrition",
}

VALID_PACKAGE_TYPES = frozenset(
    {
        PACKAGE_TYPE_FSSAI,
        PACKAGE_TYPE_BASIC_NUTRITION,
        PACKAGE_TYPE_NUTRITION_ONLY,
        PACKAGE_TYPE_DETAILED_NUTRITION,
    }
)
PACKAGE_TYPE_LABELS = [
    PACKAGE_TYPES[PACKAGE_TYPE_FSSAI],
    PACKAGE_TYPES[PACKAGE_TYPE_BASIC_NUTRITION],
    PACKAGE_TYPES[PACKAGE_TYPE_DETAILED_NUTRITION],
]
LABEL_TO_PACKAGE_TYPE = {v: k for k, v in PACKAGE_TYPES.items()}
LABEL_TO_PACKAGE_TYPE["Nutrition Only"] = PACKAGE_TYPE_NUTRITION_ONLY

CTR_PARAMETER_OTHER = "Other"
CTR_PARAMETER_OPTIONS = [
    PACKAGE_TYPES[PACKAGE_TYPE_FSSAI],
    PACKAGE_TYPES[PACKAGE_TYPE_BASIC_NUTRITION],
    PACKAGE_TYPES[PACKAGE_TYPE_DETAILED_NUTRITION],
    CTR_PARAMETER_OTHER,
]
# Canonical keys after normalize (nutrition_only → basic_nutrition)
PACKAGE_TYPE_ALIASES: dict[str, str] = {
    PACKAGE_TYPE_NUTRITION_ONLY: PACKAGE_TYPE_BASIC_NUTRITION,
}

LOGO_SCOPE_WITH = "with_logo"
LOGO_SCOPE_WITHOUT = "without_logo"
VALID_LOGO_SCOPES = frozenset({LOGO_SCOPE_WITH, LOGO_SCOPE_WITHOUT})


@dataclass
class TestPackage:
    """Live test package row with ordered catalog keys per report scope."""

    id: int
    sample_product_name: str
    package_type: str
    category: str
    current_version_no: int
    is_active: bool
    test_keys_with_logo: list[str] = field(default_factory=list)
    test_keys_without_logo: list[str] = field(default_factory=list)

    @property
    def test_keys(self) -> list[str]:
        """Union of with-logo and without-logo sets (stable order)."""
        return _merge_test_key_lists(
            self.test_keys_with_logo,
            self.test_keys_without_logo,
        )

    @property
    def package_type_label(self) -> str:
        return PACKAGE_TYPES.get(self.package_type, self.package_type)

    @property
    def display_label(self) -> str:
        return package_display_label(
            self.sample_product_name, self.package_type_label
        )


@dataclass
class ResolvedPackage:
    """Result of resolving a product name + package type at intake."""

    package_id: int
    package_version_no: int
    package_type: str
    sample_product_name: str
    test_keys: list[str]
    test_keys_with_logo: list[str]
    test_keys_without_logo: list[str]
    display_label: str


@dataclass
class PackageVersionDiffRow:
    """One row in a version comparison table."""

    test_key: str
    test_name: str
    in_version_a: bool
    in_version_b: bool
    change: str  # unchanged | added | removed


def is_other_parameters_label(label: Optional[str]) -> bool:
    """True when the Parameters column selectbox is set to Other."""
    return (label or "").strip() == CTR_PARAMETER_OTHER


def parameters_label_to_package_type(label: Optional[str]) -> Optional[str]:
    """Map a Parameters selectbox label to a package type key, or None for Other."""
    text = (label or "").strip()
    if not text or is_other_parameters_label(text):
        return None
    return normalize_package_type(text)


def ctr_parameters_label_for_sample(
    *,
    parameters: Optional[str] = None,
    package_type: Optional[str] = None,
) -> str:
    """Short text for the printed CTR Parameters column."""
    params = (parameters or "").strip()
    ptype = normalize_package_type(package_type) or parameters_label_to_package_type(
        params
    )
    if ptype:
        return package_type_label(ptype)
    if params in CTR_PARAMETER_OPTIONS:
        return params
    return params


def ctr_parameters_select_value(
    parameters: Optional[str],
    package_type: Optional[str],
) -> str:
    """Value for the Food Parameters selectbox when editing an existing sample."""
    label = ctr_parameters_label_for_sample(
        parameters=parameters,
        package_type=package_type,
    )
    if label and label not in CTR_PARAMETER_OPTIONS:
        return CTR_PARAMETER_OTHER
    return label


def normalize_package_type(value: Optional[str]) -> Optional[str]:
    """Return a valid package type key or None."""
    if value is None:
        return None
    text = str(value).strip()
    if text in VALID_PACKAGE_TYPES:
        return PACKAGE_TYPE_ALIASES.get(text, text)
    mapped = LABEL_TO_PACKAGE_TYPE.get(text)
    if mapped:
        return PACKAGE_TYPE_ALIASES.get(mapped, mapped)
    return None


def package_type_label(package_type: Optional[str]) -> str:
    key = normalize_package_type(package_type)
    if not key:
        return ""
    if key == PACKAGE_TYPE_BASIC_NUTRITION:
        return PACKAGE_TYPES[PACKAGE_TYPE_BASIC_NUTRITION]
    return PACKAGE_TYPES.get(key, key)


def is_nutrition_package_type(package_type: Optional[str]) -> bool:
    """Basic or Detailed Nutrition package groups (Basic Nutrition Word template)."""
    key = normalize_package_type(package_type)
    return key in (
        PACKAGE_TYPE_BASIC_NUTRITION,
        PACKAGE_TYPE_DETAILED_NUTRITION,
    )


def is_fssai_package_type(package_type: Optional[str]) -> bool:
    key = normalize_package_type(package_type)
    return key == PACKAGE_TYPE_FSSAI


def package_display_label(sample_product_name: str, package_type: str | None) -> str:
    """Human-readable label stored on sample parameters."""
    name = (sample_product_name or "").strip()
    label = package_type_label(package_type)
    if name and label:
        return f"{name} — {label} — tests to be conducted"
    if name:
        return f"{name} — tests to be conducted"
    return ""


def validate_test_keys(test_keys: list[str], category: str = CATEGORY_FOOD) -> list[str]:
    """Validate and return ordered unique keys for a Food package (non-empty)."""
    keys = _validate_key_list(test_keys, category, allow_empty=False)
    if not keys:
        raise ValueError("Select at least one catalog test for the package.")
    return keys


def validate_package_test_sets(
    test_keys_with_logo: list[str],
    test_keys_without_logo: list[str],
    category: str = CATEGORY_FOOD,
) -> tuple[list[str], list[str]]:
    """Validate disjoint with-logo / without-logo sets; at least one key total."""
    wl = _validate_key_list(test_keys_with_logo, category, allow_empty=True)
    nwl = _validate_key_list(test_keys_without_logo, category, allow_empty=True)
    if not wl and not nwl:
        raise ValueError("Select at least one catalog test for the package.")
    overlap = set(wl) & set(nwl)
    if overlap:
        names = [
            TEST_CATALOG[k].name if k in TEST_CATALOG else k for k in sorted(overlap)
        ]
        raise ValueError(
            "Tests cannot appear in both with-logo and without-logo sets: "
            + ", ".join(names)
        )
    return wl, nwl


def _validate_key_list(
    test_keys: list[str],
    category: str,
    *,
    allow_empty: bool,
) -> list[str]:
    """Validate and return ordered unique keys for one logo scope."""
    cat = normalize_category(category)
    if cat != CATEGORY_FOOD:
        raise ValueError("Test packages are only supported for Food category.")
    allowed = {t.key for t in tests_for_category(cat)}
    keys: list[str] = []
    seen: set[str] = set()
    for raw in test_keys or []:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        if key not in TEST_CATALOG:
            from services.custom_formulas import load_custom_lab_tests

            if key not in load_custom_lab_tests():
                raise ValueError(f"Unknown catalog test key: {key}")
        if key not in allowed:
            raise ValueError(f"Test '{key}' is not allowed for category '{cat}'.")
        seen.add(key)
        keys.append(key)
    if not keys and not allow_empty:
        raise ValueError("Select at least one catalog test for the package.")
    return keys


def _merge_test_key_lists(*lists: list[str]) -> list[str]:
    """Stable union of catalog key lists."""
    merged: list[str] = []
    seen: set[str] = set()
    for keys in lists:
        for key in keys or []:
            if key and key not in seen:
                seen.add(key)
                merged.append(key)
    return merged


def package_snapshot(package_id: int) -> dict[str, Any]:
    """Build JSON snapshot of a package for entity_versions."""
    pkg = get_package(package_id)
    if pkg is None:
        return {}
    return {
        "package_id": pkg.id,
        "sample_product_name": pkg.sample_product_name,
        "package_type": pkg.package_type,
        "package_type_label": pkg.package_type_label,
        "category": pkg.category,
        "version_no": pkg.current_version_no,
        "is_active": pkg.is_active,
        "test_keys": list(pkg.test_keys),
        "test_keys_with_logo": list(pkg.test_keys_with_logo),
        "test_keys_without_logo": list(pkg.test_keys_without_logo),
    }


def diff_package_versions(
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
) -> list[PackageVersionDiffRow]:
    """Compare two package snapshots; highlight added/removed tests."""
    keys_a = list(snapshot_a.get("test_keys") or [])
    keys_b = list(snapshot_b.get("test_keys") or [])
    set_a = set(keys_a)
    set_b = set(keys_b)
    all_keys: list[str] = []
    seen: set[str] = set()
    for key in keys_a + keys_b:
        if key not in seen:
            seen.add(key)
            all_keys.append(key)

    rows: list[PackageVersionDiffRow] = []
    for key in all_keys:
        in_a = key in set_a
        in_b = key in set_b
        if in_a and in_b:
            change = "unchanged"
        elif in_b:
            change = "added"
        else:
            change = "removed"
        test_name = TEST_CATALOG[key].name if key in TEST_CATALOG else get_test(key).name
        rows.append(
            PackageVersionDiffRow(
                test_key=key,
                test_name=test_name,
                in_version_a=in_a,
                in_version_b=in_b,
                change=change,
            )
        )
    return rows


def list_packages(
    *,
    sample_product_name: Optional[str] = None,
    package_type: Optional[str] = None,
    active_only: bool = True,
    limit: int = 200,
) -> list[TestPackage]:
    """List packages with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []

    if active_only:
        clauses.append("p.is_active = TRUE")
    if sample_product_name and sample_product_name.strip():
        clauses.append("lower(trim(p.sample_product_name)) = lower(trim(%s))")
        params.append(sample_product_name.strip())
    ptype = normalize_package_type(package_type)
    if ptype:
        clauses.append("p.package_type = %s")
        params.append(ptype)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 500))
    sql = f"""
        SELECT p.id, p.sample_product_name, p.package_type, p.category,
               p.current_version_no, p.is_active
          FROM sample_test_packages p
         {where}
         ORDER BY lower(trim(p.sample_product_name)), p.package_type
         LIMIT %s
    """
    params.append(lim)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                header_rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []

    packages: list[TestPackage] = []
    for row in header_rows:
        pkg = _header_to_package(row)
        wl, nwl = _load_test_sets(pkg.id)
        pkg.test_keys_with_logo = wl
        pkg.test_keys_without_logo = nwl
        packages.append(pkg)
    return packages


def get_package(package_id: int) -> Optional[TestPackage]:
    """Load one package by id."""
    sql = """
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE id = %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (package_id,))
                row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    pkg = _header_to_package(row)
    wl, nwl = _load_test_sets(pkg.id)
    pkg.test_keys_with_logo = wl
    pkg.test_keys_without_logo = nwl
    return pkg


def _find_package_by_name_type(
    sample_product_name: str,
    package_type: str,
    *,
    category: str = CATEGORY_FOOD,
    active_only: bool = False,
) -> Optional[TestPackage]:
    """Lookup package by product name + type; optionally active rows only."""
    name = (sample_product_name or "").strip()
    ptype = normalize_package_type(package_type)
    if not name or not ptype:
        return None
    cat = normalize_category(category)
    if cat != CATEGORY_FOOD:
        return None

    active_clause = "AND is_active = TRUE" if active_only else ""
    sql = f"""
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE lower(trim(sample_product_name)) = lower(trim(%s))
           AND package_type = %s
           AND category = %s
           {active_clause}
         LIMIT 1
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, ptype, cat))
                row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    pkg = _header_to_package(row)
    wl, nwl = _load_test_sets(pkg.id)
    pkg.test_keys_with_logo = wl
    pkg.test_keys_without_logo = nwl
    return pkg


def describe_sample_package(
    sample_product_name: str,
    package_type: str,
    *,
    category: str = CATEGORY_FOOD,
    pinned_package_id: Optional[int] = None,
    pinned_version_no: Optional[int] = None,
) -> dict[str, Any]:
    """
    Summarize package assignment for a Food sample row.

    Returns status: defined | not_defined | inactive, plus display metadata.
    """
    name = (sample_product_name or "").strip()
    ptype = normalize_package_type(package_type)
    result: dict[str, Any] = {
        "status": "not_defined",
        "package_id": None,
        "version_no": None,
        "display_label": "",
        "is_active": False,
        "pinned_package_id": pinned_package_id,
        "pinned_version_no": pinned_version_no,
        "version_mismatch": False,
        "wl_count": 0,
        "nwl_count": 0,
        "test_keys_with_logo": [],
        "test_keys_without_logo": [],
    }
    if not name or not ptype:
        return result

    active = resolve_package_tests(name, ptype, category=category)
    inactive_match = _find_package_by_name_type(
        name, ptype, category=category, active_only=False
    )

    if active:
        result.update(
            {
                "status": "defined",
                "package_id": active.package_id,
                "version_no": active.package_version_no,
                "display_label": active.display_label,
                "is_active": True,
                "wl_count": len(active.test_keys_with_logo),
                "nwl_count": len(active.test_keys_without_logo),
                "test_keys_with_logo": list(active.test_keys_with_logo),
                "test_keys_without_logo": list(active.test_keys_without_logo),
            }
        )
    elif inactive_match and not inactive_match.is_active:
        result.update(
            {
                "status": "inactive",
                "package_id": inactive_match.id,
                "version_no": inactive_match.current_version_no,
                "display_label": inactive_match.display_label,
                "is_active": False,
                "wl_count": len(inactive_match.test_keys_with_logo),
                "nwl_count": len(inactive_match.test_keys_without_logo),
                "test_keys_with_logo": list(inactive_match.test_keys_with_logo),
                "test_keys_without_logo": list(inactive_match.test_keys_without_logo),
            }
        )

    if pinned_package_id is not None and pinned_version_no is not None:
        current_ver = result.get("version_no")
        if current_ver is not None and int(current_ver) != int(pinned_version_no):
            result["version_mismatch"] = True
        elif result["status"] == "not_defined":
            pinned_pkg = get_package(pinned_package_id)
            if pinned_pkg:
                result["pinned_display_label"] = pinned_pkg.display_label

    return result


def package_status_label(desc: dict[str, Any]) -> str:
    """Human-readable package status for tables."""
    status = desc.get("status") or "not_defined"
    if status == "defined":
        return "Defined"
    if status == "inactive":
        return "Inactive"
    return "Not defined"


def resolve_package_tests(
    sample_product_name: str,
    package_type: str,
    *,
    category: str = CATEGORY_FOOD,
) -> Optional[ResolvedPackage]:
    """
    Find an active package by product name (case-insensitive) and package type.
    """
    name = (sample_product_name or "").strip()
    ptype = normalize_package_type(package_type)
    if not name or not ptype:
        return None
    cat = normalize_category(category)
    if cat != CATEGORY_FOOD:
        return None

    sql = """
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE lower(trim(sample_product_name)) = lower(trim(%s))
           AND package_type = %s
           AND category = %s
           AND is_active = TRUE
         LIMIT 1
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, ptype, cat))
                row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None

    pkg = _header_to_package(row)
    wl, nwl = _load_test_sets(pkg.id)
    pkg.test_keys_with_logo = wl
    pkg.test_keys_without_logo = nwl
    if not pkg.test_keys:
        return None

    return _package_to_resolved(pkg)


def _package_to_resolved(pkg: TestPackage) -> ResolvedPackage:
    """Build intake lookup result from a loaded package row."""
    return ResolvedPackage(
        package_id=pkg.id,
        package_version_no=pkg.current_version_no,
        package_type=pkg.package_type,
        sample_product_name=pkg.sample_product_name,
        test_keys=list(pkg.test_keys),
        test_keys_with_logo=list(pkg.test_keys_with_logo),
        test_keys_without_logo=list(pkg.test_keys_without_logo),
        display_label=pkg.display_label,
    )


def resolve_package_for_product(
    sample_product_name: str,
    *,
    category: str = CATEGORY_FOOD,
) -> Optional[ResolvedPackage]:
    """
    Find the single active package for a product name at reception intake.

    Returns None when no package exists, the package has no tests, or more
    than one active package matches (legacy duplicate types).
    """
    name = (sample_product_name or "").strip()
    if not name:
        return None
    cat = normalize_category(category)
    if cat != CATEGORY_FOOD:
        return None

    sql = """
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE lower(trim(sample_product_name)) = lower(trim(%s))
           AND category = %s
           AND is_active = TRUE
         ORDER BY package_type
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, cat))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return None

    if len(rows) != 1:
        return None

    pkg = _header_to_package(rows[0])
    wl, nwl = _load_test_sets(pkg.id)
    pkg.test_keys_with_logo = wl
    pkg.test_keys_without_logo = nwl
    if not pkg.test_keys:
        return None
    return _package_to_resolved(pkg)


def describe_sample_package_for_product(
    sample_product_name: str,
    *,
    category: str = CATEGORY_FOOD,
) -> dict[str, Any]:
    """
    Summarize package assignment for intake by product name only.

    Status: defined | not_defined | inactive | ambiguous
    """
    name = (sample_product_name or "").strip()
    cat = normalize_category(category)
    result: dict[str, Any] = {
        "status": "not_defined",
        "package_id": None,
        "version_no": None,
        "display_label": "",
        "is_active": False,
        "active_count": 0,
        "wl_count": 0,
        "nwl_count": 0,
        "test_keys": [],
        "test_keys_with_logo": [],
        "test_keys_without_logo": [],
        "ambiguous_types": [],
    }
    if not name or cat != CATEGORY_FOOD:
        return result

    active = resolve_package_for_product(name, category=cat)
    if active:
        result.update(
            {
                "status": "defined",
                "package_id": active.package_id,
                "version_no": active.package_version_no,
                "display_label": active.display_label,
                "is_active": True,
                "active_count": 1,
                "wl_count": len(active.test_keys_with_logo),
                "nwl_count": len(active.test_keys_without_logo),
                "test_keys": list(active.test_keys),
                "test_keys_with_logo": list(active.test_keys_with_logo),
                "test_keys_without_logo": list(active.test_keys_without_logo),
            }
        )
        return result

    sql_active = """
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE lower(trim(sample_product_name)) = lower(trim(%s))
           AND category = %s
           AND is_active = TRUE
    """
    sql_inactive = """
        SELECT id, sample_product_name, package_type, category,
               current_version_no, is_active
          FROM sample_test_packages
         WHERE lower(trim(sample_product_name)) = lower(trim(%s))
           AND category = %s
           AND is_active = FALSE
         ORDER BY current_version_no DESC, id DESC
         LIMIT 1
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_active, (name, cat))
                active_rows = cur.fetchall()
                if len(active_rows) > 1:
                    types = [
                        PACKAGE_TYPES.get(row[2], row[2]) for row in active_rows
                    ]
                    result["status"] = "ambiguous"
                    result["active_count"] = len(active_rows)
                    result["ambiguous_types"] = types
                    return result
                cur.execute(sql_inactive, (name, cat))
                inactive_row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return result

    if inactive_row:
        pkg = _header_to_package(inactive_row)
        wl, nwl = _load_test_sets(pkg.id)
        result.update(
            {
                "status": "inactive",
                "package_id": pkg.id,
                "version_no": pkg.current_version_no,
                "display_label": pkg.display_label,
                "is_active": False,
                "wl_count": len(wl),
                "nwl_count": len(nwl),
                "test_keys": list(pkg.test_keys),
                "test_keys_with_logo": wl,
                "test_keys_without_logo": nwl,
            }
        )
    return result


def create_package(
    sample_product_name: str,
    package_type: str,
    test_keys_with_logo: list[str],
    test_keys_without_logo: list[str] | None = None,
    *,
    category: str = CATEGORY_FOOD,
    actor=None,
) -> TestPackage:
    """Create a new test package at version 1."""
    name = (sample_product_name or "").strip()
    if not name:
        raise ValueError("Sample product name is required.")
    ptype = normalize_package_type(package_type)
    if not ptype:
        raise ValueError("Valid package type is required.")
    cat = normalize_category(category)
    wl, nwl = validate_package_test_sets(
        test_keys_with_logo,
        test_keys_without_logo or [],
        cat,
    )

    insert_pkg = """
        INSERT INTO sample_test_packages (
            sample_product_name, package_type, category, current_version_no, is_active
        )
        VALUES (%s, %s, %s, 1, TRUE)
        RETURNING id, sample_product_name, package_type, category,
                  current_version_no, is_active
    """
    insert_test = """
        INSERT INTO sample_test_package_tests (
            package_id, test_key, sort_order, logo_scope
        )
        VALUES (%s, %s, %s, %s)
    """

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_pkg, (name, ptype, cat))
                row = cur.fetchone()
                package_id = int(row[0])
                _insert_package_tests(cur, insert_test, package_id, wl, nwl)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ValueError(
                f"A package already exists for '{name}' "
                f"({PACKAGE_TYPES[ptype]})."
            ) from exc
        raise

    total = len(wl) + len(nwl)
    log_from_user(
        actor,
        "package.create",
        ENTITY_TABLE,
        package_id,
        details=(
            f"{name} / {PACKAGE_TYPES[ptype]} / "
            f"WL:{len(wl)} NWL:{len(nwl)} ({total} tests)"
        ),
    )
    pkg = _header_to_package(row)
    pkg.test_keys_with_logo = wl
    pkg.test_keys_without_logo = nwl
    return pkg


def update_package(
    package_id: int,
    test_keys_with_logo: list[str],
    test_keys_without_logo: list[str],
    edit_reason: str,
    *,
    sample_product_name: Optional[str] = None,
    actor=None,
) -> TestPackage:
    """Update package tests; archives prior state as a new version."""
    validate_edit_reason(edit_reason)
    existing = get_package(package_id)
    if existing is None:
        raise ValueError(f"Package #{package_id} was not found.")
    if not existing.is_active:
        raise ValueError("Cannot update an inactive package.")

    wl, nwl = validate_package_test_sets(
        test_keys_with_logo,
        test_keys_without_logo,
        existing.category,
    )
    new_name = (sample_product_name or "").strip() or existing.sample_product_name

    save_version(
        ENTITY_TABLE,
        package_id,
        package_snapshot(package_id),
        edit_reason,
        actor=actor,
    )

    new_version = existing.current_version_no + 1
    deactivate_sql = """
        UPDATE sample_test_packages
           SET is_active = FALSE, updated_at = NOW()
         WHERE id = %s
    """
    insert_pkg = """
        INSERT INTO sample_test_packages (
            sample_product_name, package_type, category,
            current_version_no, is_active
        )
        VALUES (%s, %s, %s, %s, TRUE)
        RETURNING id
    """
    insert_test = """
        INSERT INTO sample_test_package_tests (
            package_id, test_key, sort_order, logo_scope
        )
        VALUES (%s, %s, %s, %s)
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(deactivate_sql, (package_id,))
            cur.execute(
                insert_pkg,
                (new_name, existing.package_type, existing.category, new_version),
            )
            new_row = cur.fetchone()
            new_package_id = int(new_row[0])
            _insert_package_tests(cur, insert_test, new_package_id, wl, nwl)

    total = len(wl) + len(nwl)
    log_from_user(
        actor,
        "package.update",
        ENTITY_TABLE,
        new_package_id,
        details=(
            f"v{new_version} from #{package_id} / "
            f"WL:{len(wl)} NWL:{len(nwl)} ({total} tests)"
        ),
        edit_reason=edit_reason,
    )
    updated = get_package(new_package_id)
    if updated is None:
        raise RuntimeError("Package update succeeded but reload failed.")
    return updated


def delete_package(package_id: int, edit_reason: str, *, actor=None) -> None:
    """Soft-delete a package after archiving a version snapshot."""
    validate_edit_reason(edit_reason)
    existing = get_package(package_id)
    if existing is None:
        raise ValueError(f"Package #{package_id} was not found.")
    if not existing.is_active:
        return

    pending = _count_pending_sample_references(package_id)
    if pending:
        raise ValueError(
            f"Cannot delete: package is assigned to {pending} pending sample(s)."
        )

    save_version(
        ENTITY_TABLE,
        package_id,
        package_snapshot(package_id),
        edit_reason,
        actor=actor,
    )

    sql = """
        UPDATE sample_test_packages
           SET is_active = FALSE, updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (package_id,))

    log_from_user(
        actor,
        "package.delete",
        ENTITY_TABLE,
        package_id,
        edit_reason=edit_reason,
    )


def activate_package(package_id: int, edit_reason: str, *, actor=None) -> TestPackage:
    """Re-activate a deactivated package after archiving a version snapshot."""
    validate_edit_reason(edit_reason)
    existing = get_package(package_id)
    if existing is None:
        raise ValueError(f"Package #{package_id} was not found.")
    if existing.is_active:
        raise ValueError("Package is already active.")

    conflict = _find_package_by_name_type(
        existing.sample_product_name,
        existing.package_type,
        category=existing.category,
        active_only=True,
    )
    if conflict is not None and conflict.id != package_id:
        raise ValueError(
            f"Cannot activate: an active package already exists for "
            f"'{existing.sample_product_name}' ({existing.package_type_label})."
        )

    save_version(
        ENTITY_TABLE,
        package_id,
        package_snapshot(package_id),
        edit_reason,
        actor=actor,
    )

    sql = """
        UPDATE sample_test_packages
           SET is_active = TRUE, updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (package_id,))

    log_from_user(
        actor,
        "package.activate",
        ENTITY_TABLE,
        package_id,
        edit_reason=edit_reason,
    )
    activated = get_package(package_id)
    if activated is None:
        raise RuntimeError("Package activation succeeded but reload failed.")
    return activated


def list_package_versions(package_id: int, limit: int = 50) -> list:
    """Return version rows for a package, newest first."""
    return list_versions(
        entity_table=ENTITY_TABLE,
        entity_id=str(package_id),
        limit=limit,
    )


def get_package_version_snapshot(package_id: int, version_no: int) -> Optional[dict]:
    """Load a specific historical snapshot by version number."""
    for ver in list_package_versions(package_id, limit=500):
        snap = ver.snapshot()
        if int(snap.get("version_no") or ver.version_no) == int(version_no):
            return snap
    return None


def build_current_version_snapshot(package_id: int) -> dict[str, Any]:
    """Snapshot of the live package (for comparing with historical versions)."""
    return package_snapshot(package_id)


def _count_pending_sample_references(package_id: int) -> int:
    sql = """
        SELECT COUNT(*)
          FROM request_samples
         WHERE package_id = %s AND status = 'pending'
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (package_id,))
                row = cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0


def _load_test_sets(package_id: int) -> tuple[list[str], list[str]]:
    sql = """
        SELECT test_key, COALESCE(logo_scope, 'with_logo')
          FROM sample_test_package_tests
         WHERE package_id = %s
         ORDER BY sort_order, test_key
    """
    with_logo: list[str] = []
    without_logo: list[str] = []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (package_id,))
                for test_key, scope in cur.fetchall():
                    key = str(test_key)
                    if scope == LOGO_SCOPE_WITHOUT:
                        without_logo.append(key)
                    else:
                        with_logo.append(key)
    except Exception:  # noqa: BLE001
        return [], []
    return with_logo, without_logo


def _insert_package_tests(
    cur,
    insert_sql: str,
    package_id: int,
    with_logo: list[str],
    without_logo: list[str],
) -> None:
    order = 0
    for key in with_logo:
        cur.execute(insert_sql, (package_id, key, order, LOGO_SCOPE_WITH))
        order += 1
    for key in without_logo:
        cur.execute(insert_sql, (package_id, key, order, LOGO_SCOPE_WITHOUT))
        order += 1


def _header_to_package(row: tuple) -> TestPackage:
    return TestPackage(
        id=int(row[0]),
        sample_product_name=row[1] or "",
        package_type=row[2] or "",
        category=row[3] or CATEGORY_FOOD,
        current_version_no=int(row[4] or 1),
        is_active=bool(row[5]),
    )


def filter_resolved_keys(keys: list[str], category: str) -> list[str]:
    """Filter resolved package keys for a sample category."""
    return filter_keys_for_category(keys, category)
