"""
scripts/wipe_customer_by_gst.py
-------------------------------
Remove a manual QA / dummy-test customer and all intake data by GST number.

Only GSTINs used for QA and pytest are allowed (prefix 99MANUAL, 99DB, 99TEST,
or integration-style ``99…1Z5``). Real client GSTINs are rejected.

Usage
-----
  python scripts/wipe_customer_by_gst.py --gst 99MANUAL0001A1Z5
  python scripts/wipe_customer_by_gst.py --gst 99MANUAL0001A1Z5 --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.connection import get_db, test_connection  # noqa: E402


def _normalize_gst(gst: str) -> str:
    return (gst or "").strip().upper()


_DELETABLE_GST_PREFIXES = ("99MANUAL", "99DB", "99TEST")
_INTEGRATION_GST_RE = re.compile(r"^99[A-Z0-9]{10,}1Z5$")

_GST_GUARD_MESSAGE = (
    "Refusing to delete: GST must be a dummy/test GSTIN "
    "(prefix 99MANUAL, 99DB, or 99TEST, or integration pattern 99…1Z5). "
    "Real client GSTINs are not allowed."
)


def is_deletable_test_gst(gst: str) -> bool:
    """True when GST is a known dummy/test pattern used in this repo."""
    normalized = _normalize_gst(gst)
    if not normalized:
        return False
    if normalized.startswith(_DELETABLE_GST_PREFIXES):
        return True
    return bool(_INTEGRATION_GST_RE.match(normalized))


def _require_deletable_test_gst(gst: str) -> str:
    normalized = _normalize_gst(gst)
    if not normalized:
        raise ValueError("GST number is required")
    if not is_deletable_test_gst(normalized):
        raise ValueError(_GST_GUARD_MESSAGE)
    return normalized


def wipe_customer_by_gst(*, gst: str, dry_run: bool = False) -> dict[str, int]:
    normalized = _require_deletable_test_gst(gst)

    counts = {"requests_deleted": 0, "customers_deleted": 0}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, customer_name FROM customers WHERE gst_number = %s",
                (normalized,),
            )
            row = cur.fetchone()
            if row is None:
                return counts
            customer_id, customer_name = row[0], row[1]

            cur.execute(
                "SELECT COUNT(*) FROM test_requests WHERE customer_id = %s",
                (customer_id,),
            )
            request_count = int(cur.fetchone()[0])

            if dry_run:
                print(
                    f"Dry run: would delete {request_count} test_request(s) "
                    f"and customer #{customer_id} ({customer_name!r}, GST {normalized})"
                )
                counts["requests_deleted"] = request_count
                counts["customers_deleted"] = 1
                return counts

            cur.execute(
                "DELETE FROM test_requests WHERE customer_id = %s",
                (customer_id,),
            )
            counts["requests_deleted"] = cur.rowcount

            cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
            counts["customers_deleted"] = cur.rowcount

        conn.commit()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove customer and all test requests/samples by GST."
    )
    parser.add_argument("--gst", required=True, help="Customer GSTIN")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ok, msg = test_connection()
    if not ok:
        print(f"Database not available: {msg}", file=sys.stderr)
        sys.exit(1)

    try:
        counts = wipe_customer_by_gst(gst=args.gst, dry_run=args.dry_run)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if counts["customers_deleted"] == 0 and not args.dry_run:
        print(f"No customer found with GST {_normalize_gst(args.gst)}.")
        return

    if not args.dry_run:
        print(
            f"Removed {counts['requests_deleted']} test_request(s) and "
            f"{counts['customers_deleted']} customer(s) for GST {_normalize_gst(args.gst)}."
        )


if __name__ == "__main__":
    main()
