"""
scripts/seed_admin.py
---------------------
Apply auth migration and ensure default admin exists.

Default credentials (change after first login if desired):
  username: admin
  password: Admin@123

Usage
-----
  python scripts/seed_admin.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.connection import get_connection_params, get_db  # noqa: E402
from services.auth import ensure_default_admin  # noqa: E402


def apply_migrate_auth() -> None:
    migrate_path = ROOT / "scripts" / "migrate_auth.sql"
    if not migrate_path.exists():
        raise SystemExit(f"Migration file missing: {migrate_path}")

    sql = migrate_path.read_text(encoding="utf-8")
    params = get_connection_params()
    print(
        f"Connecting to {params['host']}:{params['port']} / db={params['dbname']} …"
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Auth migration applied.")


def main() -> None:
    apply_migrate_auth()
    created = ensure_default_admin()
    if created:
        print("Default admin created: username=admin password=Admin@123")
    else:
        print("Default admin already exists (left unchanged).")


if __name__ == "__main__":
    main()
