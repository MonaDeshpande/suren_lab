"""
scripts/seed_admin.py
---------------------
Apply idempotent schema migrations and ensure default admin exists.

Default credentials (change after first login if desired):
  username: admin
  password: Admin@123

Usage
-----
  python scripts/seed_admin.py

Note: the Streamlit app also calls ensure_schema() on startup/login so an
older Docker volume does not miss tables like user_roles.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.connection import get_connection_params  # noqa: E402
from db.migrate import ensure_schema  # noqa: E402
from services.auth import ensure_default_admin  # noqa: E402


def main() -> None:
    params = get_connection_params()
    print(
        f"Connecting to {params['host']}:{params['port']} / db={params['dbname']} …"
    )
    applied = ensure_schema(force=True)
    for name in applied:
        print(f"Applied {name}")
    created = ensure_default_admin()
    if created:
        print("Default admin created: username=admin password=Admin@123")
    else:
        print("Default admin already exists (left unchanged).")


if __name__ == "__main__":
    main()
