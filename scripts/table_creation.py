"""
scripts/table_creation.py
-------------------------
Create or update all application tables and columns (idempotent).

Applies the full base schema, then runs SQL migrations for objects not in schema.sql.

Usage
-----
  python scripts/table_creation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.connection import get_connection_params, get_db  # noqa: E402
from db.migrate import ensure_schema  # noqa: E402


def main() -> None:
    schema_path = ROOT / "db" / "schema.sql"
    if not schema_path.exists():
        raise SystemExit(f"Schema file missing: {schema_path}")

    params = get_connection_params()
    print(
        f"Connecting to {params['host']}:{params['port']} / db={params['dbname']} …"
    )

    sql = schema_path.read_text(encoding="utf-8")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Base schema applied (db/schema.sql).")

    applied = ensure_schema(force=True)
    if applied:
        for name in applied:
            print(f"Migration applied: {name}")
    else:
        print("Migrations: already up to date.")

    print("Database tables and columns are ready.")
    print("Next (first install only): python scripts/seed_admin.py")


if __name__ == "__main__":
    main()
