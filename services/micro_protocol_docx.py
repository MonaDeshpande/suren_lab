"""
services/micro_protocol_docx.py
-------------------------------
Fill reference/Micro Protocol.docx for Micro category analyst protocol.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document

from services.document_templates import MICRO_PROTOCOL_PATH
from services.docx_layout import finalize_docx_document
from services.catalog_specs import get_spec
from services.micro_report_catalog import MICRO_END_OF_REPORT, spec_for_key
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import MICRO_TEST_KEYS
from services.samples import SampleRecord

MICRO_PROTOCOL_TEMPLATE = MICRO_PROTOCOL_PATH


def suggest_micro_protocol_filename(sample: SampleRecord) -> str:
    code = (sample.sample_code or "sample").replace("/", "-")
    return f"Micro_Protocol_{code}.docx"


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _set_cell(cell, text: str) -> None:
    if not cell.paragraphs:
        cell.add_paragraph()
    cell.paragraphs[0].text = text or ""
    for para in cell.paragraphs[1:]:
        para.text = ""


def _result_display(result: Optional[TestResultRow]) -> str:
    if result is None:
        return ""
    value = (result.result_value or "").strip()
    unit = (result.unit or "").strip()
    if value and unit and unit.lower() not in value.lower():
        return f"{value} {unit}".strip()
    return value


def fill_micro_protocol_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    *,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """Produce a filled Micro protocol .docx from the reference template."""
    if not MICRO_PROTOCOL_TEMPLATE.exists():
        raise FileNotFoundError(
            f"Micro protocol template missing: {MICRO_PROTOCOL_TEMPLATE}"
        )

    doc = Document(io.BytesIO(MICRO_PROTOCOL_TEMPLATE.read_bytes()))
    tables = doc.tables
    if len(tables) < 3:
        raise ValueError("Micro protocol template must have at least 3 tables.")

    by_key = {r.test_key: r for r in results}

    # Table 0 — Protocol No / Issued to / Issued by
    t0 = tables[0]
    if t0.rows and len(t0.rows[0].cells) >= 6:
        row = t0.rows[0]
        _set_cell(row.cells[1], header.protocol_no or "")
        _set_cell(row.cells[3], header.issued_to or "")
        _set_cell(row.cells[5], header.issued_by or "")

    # Table 1 — Sample info
    t1 = tables[1]
    if len(t1.rows) >= 2 and len(t1.columns) >= 4:
        _set_cell(t1.rows[0].cells[1], sample.sample_name or "")
        _set_cell(
            t1.rows[0].cells[3],
            _fmt_date(header.sample_received_on or sample.created_at),
        )
        _set_cell(t1.rows[1].cells[1], sample.sample_code or "")
        _set_cell(
            t1.rows[1].cells[3],
            _fmt_date(header.date_of_analysis),
        )

    # Table 2 — Results (rows 2–7 = tests 1–6)
    t2 = tables[2]
    for index, key in enumerate(MICRO_TEST_KEYS):
        row_idx = index + 2
        if row_idx >= len(t2.rows):
            break
        spec = spec_for_key(key)
        db_spec = get_spec(key)
        name = db_spec.test_name if db_spec else spec.name
        method = db_spec.method_of_analysis if db_spec else spec.method
        row = t2.rows[row_idx]
        _set_cell(row.cells[0], str(index + 1))
        _set_cell(row.cells[1], name)
        _set_cell(row.cells[2], _result_display(by_key.get(key)))
        _set_cell(row.cells[3], method)

    finalize_docx_document(doc, set_qsf=False)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
