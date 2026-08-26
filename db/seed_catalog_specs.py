"""
db/seed_catalog_specs.py
------------------------
Idempotent seed of catalog_test_specs from built-in Python catalogs.
"""

from __future__ import annotations

from db.connection import get_db
from services.micro_report_catalog import MICRO_REPORT_SPECS
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    FOOD_TEST_KEYS,
    MICRO_TEST_KEYS,
    TEST_CATALOG,
    WATER_MICRO_TEST_KEYS,
    WATER_TEST_KEYS,
)
from services.water_report_catalog import (
    WATER_REPORT_LIMITS,
    WATER_REPORT_METHOD_LABELS,
    WATER_REPORT_TEST_NAMES,
)

MICRO_FIXED_UNIT_KEYS = frozenset({"total_plate_count", "t_coliform"})
MICRO_FIXED_UNIT = "cfu/gm"


def _builtin_seed_rows() -> list[dict]:
    rows: list[dict] = []

    for index, key in enumerate(FOOD_TEST_KEYS, start=1):
        test = TEST_CATALOG.get(key)
        if test is None:
            continue
        rows.append(
            {
                "test_key": key,
                "category": CATEGORY_FOOD,
                "test_name": test.name,
                "method_of_analysis": test.method or "",
                "limits_text": None,
                "limits_desirable": None,
                "limits_permissible": None,
                "default_unit": test.unit or "",
                "unit_editable": False,
                "sort_order": index,
            }
        )

    water_keys = list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS)
    for index, key in enumerate(water_keys, start=1):
        test = TEST_CATALOG.get(key)
        if test is None:
            continue
        limits = WATER_REPORT_LIMITS.get(key)
        rows.append(
            {
                "test_key": key,
                "category": CATEGORY_WATER,
                "test_name": WATER_REPORT_TEST_NAMES.get(key, test.name),
                "method_of_analysis": WATER_REPORT_METHOD_LABELS.get(
                    key, test.method or ""
                ),
                "limits_text": None,
                "limits_desirable": limits.desirable if limits else None,
                "limits_permissible": limits.permissible if limits else None,
                "default_unit": test.unit or "",
                "unit_editable": False,
                "sort_order": index,
            }
        )

    for index, key in enumerate(MICRO_TEST_KEYS, start=1):
        test = TEST_CATALOG.get(key)
        spec = MICRO_REPORT_SPECS.get(key)
        if test is None:
            continue
        fixed_unit = key in MICRO_FIXED_UNIT_KEYS
        rows.append(
            {
                "test_key": key,
                "category": CATEGORY_MICRO,
                "test_name": spec.name if spec else test.name,
                "method_of_analysis": spec.method if spec else (test.method or ""),
                "limits_text": spec.limits if spec else None,
                "limits_desirable": None,
                "limits_permissible": None,
                "default_unit": MICRO_FIXED_UNIT if fixed_unit else "",
                "unit_editable": not fixed_unit,
                "sort_order": index,
            }
        )

    return rows


def seed_builtin_specs() -> int:
    """
    Insert built-in catalog rows when missing.

    Returns number of rows inserted this call.
    """
    rows = _builtin_seed_rows()
    if not rows:
        return 0

    sql = """
        INSERT INTO catalog_test_specs (
            test_key, category, test_name, method_of_analysis,
            limits_text, limits_desirable, limits_permissible,
            default_unit, unit_editable, sort_order, is_active,
            current_version_no
        )
        VALUES (
            %(test_key)s, %(category)s, %(test_name)s, %(method_of_analysis)s,
            %(limits_text)s, %(limits_desirable)s, %(limits_permissible)s,
            %(default_unit)s, %(unit_editable)s, %(sort_order)s, TRUE, 1
        )
        ON CONFLICT (test_key) DO NOTHING
    """
    inserted = 0
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(sql, row)
                    inserted += cur.rowcount
    except Exception:  # noqa: BLE001
        # Table may not exist yet during partial migrations.
        return 0
    return inserted
