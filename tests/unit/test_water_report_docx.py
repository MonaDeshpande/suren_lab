"""Unit tests for water final report DOCX generation."""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pytest
from docx import Document

from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord, water_report_keys
from services.test_report_water_docx import (
    WATER_REPORT_TEMPLATE_PATH,
    WaterReportFillOptions,
    fill_water_test_report_docx_bytes,
)
from services.water_report_catalog import (
    WATER_MICRO_PLACEHOLDERS,
    WATER_REPORT_LIMITS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS-260721-0002",
        sr_no=1,
        sample_name="Potable Water",
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="water",
        tests_json=json.dumps(
            [
                "ph",
                "tds",
                "chlorides",
                "total_alkalinity",
                "conductivity",
                "total_hardness",
                "calcium_ca",
                "calcium_caco3",
                "magnesium",
                "odor",
                "turbidity",
            ]
        ),
        lab_code="SLS/26/638/01",
        customer_name="Test Customer",
        customer_address="Pune",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    base.update(overrides)
    return SampleRecord(**base)


def _header() -> ProtocolHeader:
    return ProtocolHeader(
        sample_id=1,
        protocol_no="P-001",
        issued_to="Analyst",
        issued_by="Reception",
        sample_received_on=date(2026, 7, 27),
        date_of_analysis=date(2026, 7, 30),
        appearance_text="Colorless transparent liquid",
    )


def _cell_text(cell) -> str:
    return "\n".join(p.text for p in cell.paragraphs).strip()


@pytest.mark.skipif(
    not WATER_REPORT_TEMPLATE_PATH.exists(),
    reason="Water test report template missing",
)
class TestWaterReportDocx:
    def test_calcium_caco3_excluded_from_report_keys(self):
        keys = water_report_keys(_sample())
        assert "calcium_caco3" not in keys
        assert "calcium_ca" in keys

    def test_generates_docx_with_chemical_result(self):
        results = [
            TestResultRow(
                test_key="ph",
                test_name="pH",
                method="IS 3025 : Part 11",
                unit="",
                inputs={},
                result_value="7.320",
                result_numeric=7.32,
            )
        ]
        out = fill_water_test_report_docx_bytes(_sample(), _header(), results)
        doc = Document(io.BytesIO(out))
        chem_table = doc.tables[1]
        assert "7.320" in _cell_text(chem_table.rows[3].cells[2])
        assert WATER_REPORT_LIMITS["ph"].desirable in _cell_text(chem_table.rows[3].cells[3])

    def test_micro_rows_present_with_blank_results(self):
        out = fill_water_test_report_docx_bytes(_sample(), _header(), [])
        doc = Document(io.BytesIO(out))
        micro_table = doc.tables[4]
        assert len(micro_table.rows) >= 4
        for i, placeholder in enumerate(WATER_MICRO_PLACEHOLDERS):
            row = micro_table.rows[2 + i]
            assert placeholder.name in _cell_text(row.cells[1])
            assert _cell_text(row.cells[2]) == ""

    def test_appearance_and_customer_info_filled(self):
        opts = WaterReportFillOptions(
            condition_of_sample="Packed in plastic container",
            customer_sample_id="Drinking Water",
        )
        out = fill_water_test_report_docx_bytes(
            _sample(), _header(), [], opts=opts
        )
        doc = Document(io.BytesIO(out))
        info = doc.tables[0]
        assert "Colorless transparent liquid" in _cell_text(info.rows[7].cells[1])
        assert "Packed in plastic container" in _cell_text(info.rows[6].cells[1])
        assert "Drinking Water" in _cell_text(info.rows[1].cells[1])

    def test_physical_section_fills_odor(self):
        results = [
            TestResultRow(
                test_key="odor",
                test_name="Odor",
                method="IS 3025 : Part 5",
                unit="",
                inputs={},
                result_value="Agreeable",
                result_numeric=None,
            )
        ]
        out = fill_water_test_report_docx_bytes(_sample(), _header(), results)
        doc = Document(io.BytesIO(out))
        physical = doc.tables[3]
        assert "Agreeable" in _cell_text(physical.rows[3].cells[2])
