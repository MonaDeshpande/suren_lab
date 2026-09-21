"""Unit tests for Reviewer final-report default fields."""

from __future__ import annotations

import json

from services.protocol_store import ProtocolHeader
from services.reviewer_report_defaults import (
    default_customer_sample_id_for_report,
    default_reviewer_report_fields,
)
from services.samples import SampleRecord


def _sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS/26/306/01",
        sr_no=1,
        sample_name="Jaggery",
        batch_code="B-01",
        quantity="500 g",
        parameters="FSSAI",
        tests_to_perform="",
        status="completed",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json=json.dumps(["moisture"]),
        lab_code="SLS/26/306",
        customer_name="ABC Foods",
        customer_address="Pune",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
        sampling_by_lab=False,
        package_type="fssai",
    )
    base.update(overrides)
    return SampleRecord(**base)


def test_default_customer_sample_id_food_uses_sample_name():
    assert default_customer_sample_id_for_report(_sample()) == "Jaggery"


def test_default_reviewer_report_fields_prefill_from_reception():
    header = ProtocolHeader(sample_id=1)
    fields = default_reviewer_report_fields(_sample(), header)
    assert fields["customer_sid"] == "Jaggery"
    assert fields["batch_no"] == "B-01"
    assert fields["lab_code"] == "SLS/26/306/01"
    assert "ABC Foods" in fields["customer_addr"]
    assert fields["ulr"].startswith("TC16118")
