"""Unit tests for CTR verification checklist helpers."""

from __future__ import annotations

from datetime import date

from services.ctr_verification import (
    ctr_test_names_for_sample,
    verification_checklist_rows,
    verification_yes_no_remark,
)
from services.requests import SampleRow


def test_verification_yes_no_remark():
    assert verification_yes_no_remark(True) == "Yes ( X ) No (  )"
    assert verification_yes_no_remark(False) == "Yes (  ) No ( X )"
    assert verification_yes_no_remark(None) == "Yes (  ) No (  )"


def test_ctr_test_names_from_keys():
    sample = SampleRow(
        sr_no=1,
        sample_name="Jaggery",
        test_keys=["moisture", "total_ash"],
        category="food",
    )
    assert ctr_test_names_for_sample(sample) == [
        "Moisture",
        "Total ash on dry basis",
    ]


def test_verification_checklist_has_ten_rows():
    sample = SampleRow(
        sr_no=1,
        verify_review_date=date(2026, 7, 30),
        verify_lab_code="LAB/001",
        verify_sample_condition="Ambient",
        verify_qty_checked=True,
        verify_conformity_statement=False,
    )
    rows = verification_checklist_rows(sample)
    assert len(rows) == 10
    assert rows[0].remark == "30/07/2026"
    assert rows[1].remark == "LAB/001"
    assert rows[3].remark == "Yes ( X ) No (  )"
    assert rows[9].remark == "Yes (  ) No ( X )"
