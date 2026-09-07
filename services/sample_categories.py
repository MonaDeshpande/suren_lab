"""
services/sample_categories.py
-----------------------------
Built-in and admin-defined sample categories for intake and custom formulas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from db.connection import get_db
from services.protocols.test_catalog import (
    CATEGORY_CATTLE_FEED_FERTILIZER,
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
)

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

BUILTIN_SAMPLE_CATEGORIES: dict[str, str] = {
    CATEGORY_FOOD: "Food",
    CATEGORY_WATER: "Water",
    CATEGORY_CATTLE_FEED_FERTILIZER: "Cattle Feed / Fertilizer",
    CATEGORY_MICRO: "Micro",
}


@dataclass
class SampleCategory:
    category_key: str
    label: str
    is_builtin: bool = False
    is_active: bool = True
    sort_order: int = 100


def _normalize_key(key: str) -> str:
    return (key or "").strip().lower().replace(" ", "_").replace("-", "_")


def is_valid_category_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return bool(normalized and _KEY_PATTERN.match(normalized))


def list_categories(*, active_only: bool = True) -> list[SampleCategory]:
    clauses = ["1=1"]
    params: list[object] = []
    if active_only:
        clauses.append("is_active = TRUE")
    sql = f"""
        SELECT category_key, label, is_builtin, is_active, sort_order
          FROM sample_categories
         WHERE {' AND '.join(clauses)}
         ORDER BY sort_order, label
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    except Exception:
        rows = []
    if not rows:
        return [
            SampleCategory(key, label, is_builtin=True, sort_order=i * 10)
            for i, (key, label) in enumerate(BUILTIN_SAMPLE_CATEGORIES.items(), start=1)
        ]
    return [
        SampleCategory(
            category_key=row[0],
            label=row[1],
            is_builtin=bool(row[2]),
            is_active=bool(row[3]),
            sort_order=int(row[4] or 100),
        )
        for row in rows
    ]


def all_sample_categories(*, include_inactive: bool = False) -> dict[str, str]:
    """Merged category key → label map (built-ins + DB rows)."""
    merged = dict(BUILTIN_SAMPLE_CATEGORIES)
    for cat in list_categories(active_only=not include_inactive):
        merged[cat.category_key] = cat.label
    return merged


def category_select_options(*, active_only: bool = True) -> list[tuple[str, str]]:
    """Ordered (key, label) pairs for Reception / formula dropdowns."""
    return [
        (cat.category_key, cat.label)
        for cat in list_categories(active_only=active_only)
    ]


def normalize_sample_category(category: Optional[str]) -> str:
    key = _normalize_key(category or "")
    if not key:
        return CATEGORY_FOOD
    cats = all_sample_categories(include_inactive=True)
    if key in cats:
        return key
    if key in BUILTIN_SAMPLE_CATEGORIES:
        return key
    return CATEGORY_FOOD


def is_food_category(category: Optional[str]) -> bool:
    return normalize_sample_category(category) == CATEGORY_FOOD


def is_builtin_category_key(key: str) -> bool:
    return _normalize_key(key) in BUILTIN_SAMPLE_CATEGORIES


def create_category(
    key: str,
    label: str,
    *,
    sort_order: int = 100,
    actor=None,
) -> SampleCategory:
    from services.audit import log_from_user

    category_key = _normalize_key(key)
    if not is_valid_category_key(category_key):
        raise ValueError(
            "Category key must be 2–32 lowercase letters, digits, or underscores."
        )
    clean_label = (label or "").strip()
    if not clean_label:
        raise ValueError("Category label is required.")
    if category_key in BUILTIN_SAMPLE_CATEGORIES:
        raise ValueError("Built-in category keys cannot be re-created.")
    sql = """
        INSERT INTO sample_categories (category_key, label, is_builtin, is_active, sort_order)
        VALUES (%s, %s, FALSE, TRUE, %s)
        ON CONFLICT (category_key) DO UPDATE
           SET label = EXCLUDED.label,
               is_active = TRUE,
               updated_at = NOW()
     RETURNING category_key, label, is_builtin, is_active, sort_order
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (category_key, clean_label, sort_order))
            row = cur.fetchone()
    log_from_user(actor, "sample_category.create", "sample_categories", category_key)
    return SampleCategory(
        category_key=row[0],
        label=row[1],
        is_builtin=bool(row[2]),
        is_active=bool(row[3]),
        sort_order=int(row[4] or 100),
    )


def set_category_active(
    category_key: str,
    *,
    is_active: bool,
    actor=None,
) -> None:
    from services.audit import log_from_user

    key = _normalize_key(category_key)
    if is_builtin_category_key(key) and not is_active:
        raise ValueError("Built-in categories cannot be deactivated.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sample_categories
                   SET is_active = %s, updated_at = NOW()
                 WHERE category_key = %s
                """,
                (is_active, key),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Category '{category_key}' not found.")
    action = "sample_category.activate" if is_active else "sample_category.deactivate"
    log_from_user(actor, action, "sample_categories", key)
