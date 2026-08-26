"""Protocol precision: issued-to name, dual readings columns."""

from __future__ import annotations

import io
import json
from datetime import date

from docx import Document

from services.protocol_docx import _protocol_issued_to, fill_protocol_docx_bytes
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord


def _sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS-260721-0001",
        sr_no=1,
        sample_name="Test Sample",
        batch_code="",
        quantity="",
        parameters="",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json=json.dumps(["moisture"]),
        lab_code="LAB/CTR/26/001",
        package_type="",
        assigned_analyst_name="Priya Sharma",
    )
    base.update(overrides)
    return SampleRecord(**base)


def _header(**overrides) -> ProtocolHeader:
    base = dict(
        sample_id=1,
        protocol_no="P-001",
        issued_to="Legacy Name (legacy_user)",
        issued_by="Reception",
        sample_received_on=date(2026, 7, 21),
        date_of_analysis=date(2026, 7, 21),
        appearance_text="Normal",
    )
    base.update(overrides)
    return ProtocolHeader(**base)


def test_protocol_issued_to_prefers_sample_full_name():
    sample = _sample(assigned_analyst_name="Priya Sharma")
    header = _header(issued_to="Legacy Name (legacy_user)")
    assert _protocol_issued_to(sample, header) == "Priya Sharma"


def test_protocol_issued_to_strips_legacy_suffix_from_header():
    sample = _sample(assigned_analyst_name="")
    header = _header(issued_to="Legacy Name (legacy_user)")
    assert _protocol_issued_to(sample, header) == "Legacy Name"


def _cell_text(cell) -> str:
    return (cell.text or "").strip()


def _worksheet_table_with_text(doc: Document, needle: str):
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if needle in _cell_text(cell):
                    return table
    return None


def test_moisture_recalc_fills_second_readings_column():
    results = [
        TestResultRow(
            test_key="moisture",
            test_name="Moisture",
            method="IS 15279:2003",
            unit="%",
            inputs={
                "empty_dish": "10",
                "w1": "55.1234",
                "w": "5.01",
                "after_dry": "50",
                "w2": "54.5",
                "recalc": {
                    "empty_dish": "10",
                    "w1": "55.2",
                    "w": "5.01",
                    "after_dry": "50",
                    "w2": "54.48",
                },
            },
            result_value="6.00",
            result_numeric=6.0,
        )
    ]
    doc = Document(
        io.BytesIO(fill_protocol_docx_bytes(_sample(), _header(), results))
    )
    moisture_table = _worksheet_table_with_text(doc, "stainless steel dish")
    assert moisture_table is not None
    w1_row = moisture_table.rows[2]
    assert "55.1234" in _cell_text(w1_row.cells[1])
    assert "55.2" in _cell_text(w1_row.cells[2])
