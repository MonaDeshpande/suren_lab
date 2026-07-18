"""Smoke-check catalog formulas appear in filled protocol DOCX."""
from __future__ import annotations

import io
from datetime import date

from docx import Document

from services.protocol_docx import WORKSHEET_FORMULAS, fill_protocol_docx_bytes
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import TEST_CATALOG
from services.samples import SampleRecord


def main() -> None:
    sample = SampleRecord(
        id=1,
        request_id=1,
        sample_code="SLS-260717-0001",
        sr_no=1,
        sample_name="Jaggery",
        batch_code="B1",
        quantity="500g",
        parameters="",
        tests_to_perform="",
        status="in_progress",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        lab_code="SLS/CTR/26/001",
        tests_json=(
            '["moisture","total_ash","invert_sugar",'
            '"reducing_sugar","sulphur_dioxide"]'
        ),
    )
    header = ProtocolHeader(
        sample_id=1,
        protocol_no="P-1",
        issued_to="A",
        issued_by="B",
        sample_received_on=date.today(),
        date_of_analysis=date.today(),
        appearance_text="Brown",
    )
    results = [
        TestResultRow("moisture", "Moisture", "m", "%", {}, "5.2", 5.2),
        TestResultRow("total_ash", "Total ash", "m", "%", {}, "3.1", 3.1),
        TestResultRow("invert_sugar", "Invert", "m", "%", {}, "92", 92),
        TestResultRow("reducing_sugar", "Reducing", "m", "%", {}, "15", 15),
        TestResultRow("sulphur_dioxide", "SO2", "m", "ppm", {}, "10", 10),
    ]
    raw = fill_protocol_docx_bytes(
        sample,
        header,
        results,
        generated_by="Tester",
        generated_at="2026-07-17 21:00",
    )
    doc = Document(io.BytesIO(raw))
    blob = "\n".join(
        c.text for t in doc.tables for row in t.rows for c in row.cells
    )

    checks = [
        TEST_CATALOG["moisture"].formula_display,
        "Ash % = (W2-W1)",
        "Invert:",
        "Reducing:",
        TEST_CATALOG["sulphur_dioxide"].formula_display,
    ]
    failed = 0
    for c in checks:
        ok = c in blob or c.split(";")[0].strip() in blob
        safe = c[:70].encode("ascii", "replace").decode("ascii")
        print(("OK" if ok else "MISSING"), repr(safe))
        if not ok:
            failed += 1

    print("tables", len(doc.tables), "map", list(WORKSHEET_FORMULAS))
    for label, text in (
        ("T5 R6", doc.tables[5].rows[6].cells[0].text[:90]),
        ("T6 R6", doc.tables[6].rows[6].cells[0].text[:90]),
        ("T6 R7", doc.tables[6].rows[7].cells[0].text[:90]),
        ("T12 R6", doc.tables[12].rows[6].cells[0].text[:140]),
        ("T15 R2", doc.tables[15].rows[2].cells[0].text[:90]),
    ):
        print(label + ":", repr(text.encode("ascii", "replace").decode("ascii")))
    if failed:
        raise SystemExit(f"{failed} formula check(s) failed")
    print("smoke ok")


if __name__ == "__main__":
    main()
