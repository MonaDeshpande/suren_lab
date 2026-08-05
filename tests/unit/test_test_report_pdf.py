"""Unit tests for final test report data mapping."""

from __future__ import annotations

import json
from datetime import date

from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord
from services.test_report_pdf import (
    DEFAULT_TESTS_PROCESSED,
    build_test_report_data,
)


def _sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="GLG/26/306/01",
        sr_no=1,
        sample_name="Jaggery",
        batch_code="05",
        quantity="500gm",
        parameters="",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json=json.dumps(["moisture"]),
        lab_code="GLG/26/306",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    base.update(overrides)
    return SampleRecord(**base)


def _header(**overrides) -> ProtocolHeader:
    base = dict(
        sample_id=1,
        protocol_no="P-1",
        issued_to="Analyst",
        issued_by="Reception",
        sample_received_on=date(2026, 8, 1),
        date_of_analysis=date(2026, 8, 3),
        appearance_text="Brown",
    )
    base.update(overrides)
    return ProtocolHeader(**base)


def _moisture_result() -> TestResultRow:
    return TestResultRow(
        test_key="moisture",
        test_name="Moisture",
        method="IS 15279:2003",
        unit="%",
        inputs={},
        result_value="3.22",
        result_numeric=3.22,
    )


def test_build_test_report_data_defaults():
    data = build_test_report_data(
        _sample(),
        _header(),
        [_moisture_result()],
    )
    assert data.lab_code == "GLG/26/306/01"
    assert data.tests_processed == DEFAULT_TESTS_PROCESSED
    assert data.condition_of_sample == ""
    assert data.rows[0].specification == "Not more than 7 %"


def test_build_test_report_data_reviewer_overrides():
    data = build_test_report_data(
        _sample(),
        _header(),
        [_moisture_result()],
        condition_of_sample="Sealed pouch",
        tests_processed="Moisture only",
        specification_by_test_name={"Moisture": "Custom spec"},
    )
    assert data.condition_of_sample == "Sealed pouch"
    assert data.tests_processed == "Moisture only"
    assert data.rows[0].specification == "Custom spec"
