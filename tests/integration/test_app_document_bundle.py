"""
Full app-service document bundle per category (CTR + protocol + final report).

Runs with run_tests.bat (integration marker, not e2e). Requires PostgreSQL + Word/LibreOffice.

Artifacts: tests/output_preview/app_flow/{food,water,micro}/...
"""

from __future__ import annotations

import pytest

from tests.conftest import cleanup_test_data
from tests.integration.app_flow_helpers import run_app_flow_for_category
from tests.integration.dummy_document_helpers import assert_db_clean_for_gst

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("category", ["food", "water", "micro"])
def test_app_flow_generates_ctr_protocol_final_report_and_wipes(
    require_db,
    qa_analyst_pair,
    db_test_gst,
    category: str,
):
    chem, micro = qa_analyst_pair
    try:
        paths = run_app_flow_for_category(
            db_test_gst,
            category,
            chem.id,
            micro.id,
        )
        for kind, (docx_path, pdf_path) in paths.items():
            assert docx_path.exists() and docx_path.stat().st_size > 1000
            assert pdf_path.exists() and pdf_path.read_bytes()[:4] == b"%PDF"
            print(f"\n[{category}] {kind}:\n  {docx_path}\n  {pdf_path}")
    finally:
        cleanup_test_data(gst=db_test_gst)
    assert_db_clean_for_gst(db_test_gst)
