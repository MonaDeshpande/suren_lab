"""
scripts/init_db.py
------------------
Apply db/schema.sql to the configured PostgreSQL database.

Use this when:
  - Docker volume already existed (init scripts won't re-run), or
  - You are using a local PostgreSQL install instead of Docker.

Usage
-----
  python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root on sys.path so `db` imports work when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.connection import get_connection_params, get_db  # noqa: E402


def main() -> None:
    schema_path = ROOT / "db" / "schema.sql"
    if not schema_path.exists():
        raise SystemExit(f"Schema file missing: {schema_path}")

    sql = schema_path.read_text(encoding="utf-8")
    params = get_connection_params()
    print(
        f"Connecting to {params['host']}:{params['port']} / db={params['dbname']} …"
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

    print("Schema applied successfully.")
    print("Next: python scripts/seed_admin.py  (auth migration + default admin)")


if __name__ == "__main__":
    main()
