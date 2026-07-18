"""
CLI entry: scan S_LAB codebase and generate all validation Word documents.

Usage (from project root):
  python -m validation.generate_all
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from validation.inventory import PROJECT_ROOT, build_inventory
from validation.writers import (
    write_iq,
    write_oq,
    write_pq,
    write_risk,
    write_sop,
    write_urs,
)


def main() -> int:
    root = PROJECT_ROOT
    schema = root / "db" / "schema.sql"
    if not schema.exists():
        print(f"[ERROR] Critical file missing: {schema}")
        print("        Run this module from the S_LAB project root.")
        return 1

    stamp = datetime.now().strftime("%Y%m%d")
    out_dir = root / "docs" / "validation" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  S Testing Laboratory - Validation Document Generator")
    print("=" * 60)
    print(f"Project root : {root}")
    print(f"Output folder: {out_dir}")
    print()
    print("[1/3] Scanning codebase inventory...")
    inv = build_inventory(root)
    print(f"      Roles        : {len(inv.roles)}")
    print(f"      Pages        : {len(inv.pages)}")
    print(f"      Services     : {len(inv.services)}")
    print(f"      Tables       : {len(inv.tables)}")
    print(f"      Lab tests    : {len(inv.lab_tests)}")
    print(f"      Audit actions: {len(inv.audit_actions)}")
    print(f"      Test cases   : {len(inv.test_cases)}")
    if inv.warnings:
        for w in inv.warnings:
            print(f"      [WARN] {w}")

    print()
    print("[2/3] Writing Word documents...")
    writers = [
        ("URS", write_urs),
        ("Risk Assessment", write_risk),
        ("IQ", write_iq),
        ("OQ", write_oq),
        ("PQ", write_pq),
        ("SOP", write_sop),
    ]
    created: list[Path] = []
    try:
        for label, fn in writers:
            path = fn(inv, out_dir, stamp)
            created.append(path)
            print(f"      [OK] {label}: {path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Generation failed: {exc}")
        return 1

    print()
    print("[3/3] Done.")
    print(f"Created {len(created)} documents in:")
    print(f"  {out_dir}")
    for p in created:
        print(f"  - {p.name}")
    print()
    print("Status: DRAFT - review and sign off before use as controlled records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
