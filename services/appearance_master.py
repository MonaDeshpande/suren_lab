"""
services/appearance_master.py
-----------------------------
Master list of appearance descriptions for Analyst protocol entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from db.connection import get_db


@dataclass
class AppearanceOption:
    id: int
    appearance_text: str


def _normalized_key(text: str) -> str:
    return (text or "").strip().lower()


def list_appearances(*, active_only: bool = True, limit: int = 200) -> list[AppearanceOption]:
    """Return distinct appearance strings for dropdown population."""
    clauses = ["1=1"]
    if active_only:
        clauses.append("is_active = TRUE")
    sql = f"""
        SELECT id, appearance_text
          FROM appearance_master
         WHERE {' AND '.join(clauses)}
         ORDER BY appearance_text
         LIMIT %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (max(1, min(limit, 500)),))
                rows = cur.fetchall()
    except Exception:
        return []
    return [AppearanceOption(id=row[0], appearance_text=row[1]) for row in rows]


def search_appearances(query: str, *, limit: int = 40) -> list[AppearanceOption]:
    """
    Search master appearances by partial text (case-insensitive).

    Empty query returns the most recent alphabetical list (same as list_appearances).
    """
    cap = max(1, min(limit, 500))
    q = (query or "").strip()
    if not q:
        return list_appearances(limit=cap)

    pattern = f"%{q}%"
    sql = """
        SELECT id, appearance_text
          FROM appearance_master
         WHERE is_active = TRUE
           AND appearance_text ILIKE %s
         ORDER BY appearance_text
         LIMIT %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (pattern, cap))
                rows = cur.fetchall()
    except Exception:
        return []
    return [AppearanceOption(id=row[0], appearance_text=row[1]) for row in rows]


def get_or_create_appearance(text: str) -> AppearanceOption:
    """Insert a new appearance option when analyst enters a custom value."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Appearance text is required.")
    key = _normalized_key(cleaned)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, appearance_text
                  FROM appearance_master
                 WHERE normalized_key = %s AND is_active = TRUE
                """,
                (key,),
            )
            row = cur.fetchone()
            if row:
                return AppearanceOption(id=row[0], appearance_text=row[1])
            cur.execute(
                """
                INSERT INTO appearance_master (appearance_text, normalized_key)
                VALUES (%s, %s)
                RETURNING id, appearance_text
                """,
                (cleaned, key),
            )
            new_row = cur.fetchone()
    return AppearanceOption(id=new_row[0], appearance_text=new_row[1])
