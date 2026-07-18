"""
scripts/cleanup_expired_samples.py
----------------------------------
Delete request_samples rows whose 10-day retention window has ended.

Customers and test_requests headers are kept.

Usage
-----
  python scripts/cleanup_expired_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.samples import delete_expired_samples  # noqa: E402


def main() -> None:
    deleted = delete_expired_samples()
    print(f"Deleted {deleted} expired sample row(s).")


if __name__ == "__main__":
    main()
