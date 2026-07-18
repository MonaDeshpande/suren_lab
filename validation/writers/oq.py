"""Generate Operational Qualification (OQ) protocol Word draft."""

from __future__ import annotations

from pathlib import Path

from validation.docx_util import (
    add_cover,
    add_heading,
    add_para,
    add_signature_block,
    add_table,
    dated_filename,
    new_document,
    save_document,
)
from validation.inventory import SystemInventory


def _urs_hint(tc_id: str, inv: SystemInventory) -> str:
    """Best-effort URS category hint from TC prefix + traceability."""
    prefix = tc_id.split("-")[1] if "-" in tc_id else ""
    mapping = {
        "AUTH": "URS-AUTH-*",
        "RBAC": "URS-RBAC-*",
        "ADM": "URS-ADM-*",
        "REC": "URS-REC-*",
        "ANL": "URS-ANL-*",
        "FOR": "URS-FOR-*",
        "REV": "URS-REV-*",
        "RET": "URS-RET-*",
        "AUD": "URS-AUD-*",
        "E2E": "URS-* (E2E)",
    }
    base = mapping.get(prefix, "URS-*")
    for tr in inv.traceability:
        if tc_id in tr.manual_tc_ids.replace("…", "").replace("...", ""):
            return f"{base} | Feature: {tr.feature}"
        short = "-".join(tc_id.split("-")[:2])
        if short in tr.manual_tc_ids:
            return f"{base} | Feature: {tr.feature}"
    return base


def write_oq(inv: SystemInventory, out_dir: Path, stamp: str) -> Path:
    doc = new_document()
    add_cover(
        doc,
        doc_title="Operational Qualification (OQ) Protocol",
        doc_code="SLS-VAL-OQ",
        generated_at=inv.generated_at,
    )

    add_heading(doc, "1. Purpose", level=1)
    add_para(
        doc,
        "Demonstrate that the installed system operates according to user requirements "
        "and documented test cases. Test scripts are imported from docs/test-cases/.",
    )

    add_heading(doc, "2. Preconditions", level=1)
    add_para(doc, "IQ completed (or equivalent install verified).")
    add_para(doc, "Database running; default admin available; test users per role as needed.")
    add_para(doc, "App reachable at http://localhost:8501.")

    add_heading(doc, "3. Traceability summary", level=1)
    if inv.traceability:
        add_table(
            doc,
            ("Feature / Requirement", "Manual TC-IDs", "Automated"),
            [(t.feature, t.manual_tc_ids, t.automated) for t in inv.traceability],
        )
    else:
        add_para(doc, "TRACEABILITY.md not found or empty.")

    add_heading(doc, "4. Operational test scripts", level=1)
    add_para(
        doc,
        f"{len(inv.test_cases)} test cases parsed from docs/test-cases. "
        "Record Pass/Fail only after execution. Do not pre-fill results.",
    )

    if not inv.test_cases:
        add_para(doc, "No test cases found.")
    else:
        add_table(
            doc,
            ("TC ID", "Title", "Priority", "Type", "Source", "URS link", "Result", "Initials", "Date"),
            [
                (
                    tc.tc_id,
                    tc.title[:80],
                    tc.priority,
                    tc.tc_type,
                    tc.source_file,
                    _urs_hint(tc.tc_id, inv),
                    "",
                    "",
                    "",
                )
                for tc in inv.test_cases
            ],
        )

        add_heading(doc, "5. Detailed steps (by test case)", level=1)
        for tc in inv.test_cases:
            add_heading(doc, f"{tc.tc_id} — {tc.title}", level=2)
            add_table(
                doc,
                ("Field", "Value"),
                [
                    ("Priority", tc.priority),
                    ("Type", tc.tc_type),
                    ("Source file", tc.source_file),
                    ("URS link", _urs_hint(tc.tc_id, inv)),
                    ("Preconditions", tc.preconditions),
                    ("Steps", tc.steps),
                    ("Expected", tc.expected),
                    ("Actual result", ""),
                    ("Pass / Fail", ""),
                    ("Executed by / date", ""),
                    ("Comments", ""),
                ],
            )

    add_heading(doc, "6. Deviations", level=1)
    add_table(
        doc,
        ("Dev #", "TC ID", "Description", "Impact", "Disposition"),
        [("", "", "", "", "")],
    )

    add_signature_block(doc)
    path = out_dir / dated_filename("SLS_OQ", stamp)
    return save_document(doc, path)
