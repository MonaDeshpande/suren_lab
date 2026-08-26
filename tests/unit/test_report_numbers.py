"""Unit tests for shared final-report numbering (Food / Micro / Water)."""

from __future__ import annotations

import json

from services.samples import (
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITHOUT_LOGO,
    REPORT_FORMAT_WITH_LOGO,
    SampleRecord,
    default_test_report_no,
    report_page_label,
)


def _sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS/26/690/01",
        sr_no=1,
        sample_name="Sauce",
        batch_code="",
        quantity="100 g",
        parameters="",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json=json.dumps(["moisture"]),
        lab_code="SLS/26/690",
        report_format=REPORT_FORMAT_WITH_LOGO,
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    base.update(overrides)
    return SampleRecord(**base)


def test_with_logo_only_uses_sample_code():
    sample = _sample(sample_code="SLS/26/691/01", report_format=REPORT_FORMAT_WITH_LOGO)
    assert default_test_report_no(sample, with_logo=True) == "SLS/26/691/01"
    assert default_test_report_no(sample, with_logo=False) == "SLS/26/691/01"


def test_without_logo_only_uses_sample_code():
    sample = _sample(
        sample_code="SLS/26/692/02",
        report_format=REPORT_FORMAT_WITHOUT_LOGO,
    )
    assert default_test_report_no(sample, with_logo=False) == "SLS/26/692/02"


def test_both_appends_01_and_02():
    sample = _sample(
        sample_code="SLS/26/690/01",
        report_format=REPORT_FORMAT_BOTH,
    )
    sample2 = _sample(
        sample_code="SLS/26/690/02",
        report_format=REPORT_FORMAT_BOTH,
    )
    assert default_test_report_no(sample, with_logo=True) == "SLS/26/690/01/01"
    assert default_test_report_no(sample, with_logo=False) == "SLS/26/690/01/02"
    assert default_test_report_no(sample2, with_logo=True) == "SLS/26/690/02/01"
    assert default_test_report_no(sample2, with_logo=False) == "SLS/26/690/02/02"


def test_page_label_page_vs_pg():
    assert report_page_label(with_logo=True) == "page 1 of 1"
    assert report_page_label(with_logo=False) == "pg 1 of 1"
    assert report_page_label(with_logo=True, page=2, total=3) == "page 2 of 3"
