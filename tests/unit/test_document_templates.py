"""Unit tests for client template path resolution."""

from __future__ import annotations

from services.document_templates import (
    CTR_TEMPLATE_PATH,
    FOOD_REPORT_WITHOUT_LOGO_PATH,
    FOOD_REPORT_WITH_LOGO_PATH,
    final_report_template_path,
)


def test_final_report_with_logo_uses_primary_template():
    path = final_report_template_path("food", with_logo=True)
    assert path == FOOD_REPORT_WITH_LOGO_PATH


def test_final_report_without_logo_uses_no_logo_file_when_present():
    path = final_report_template_path("food", with_logo=False)
    if FOOD_REPORT_WITHOUT_LOGO_PATH.exists():
        assert path == FOOD_REPORT_WITHOUT_LOGO_PATH
    else:
        assert path == FOOD_REPORT_WITH_LOGO_PATH


def test_ctr_template_path_under_reference():
    assert CTR_TEMPLATE_PATH.name == "Customer Test Request form LLP.docx"
    assert CTR_TEMPLATE_PATH.parent.name == "reference"
