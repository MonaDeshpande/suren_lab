"""
Integration test for service-layer E2E (Reception -> Analyst -> Reviewer).

Run: pytest -m integration tests/integration/test_e2e_app_flow.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document

from services.e2e_app_flow import (
    build_demo_scenarios,
    cleanup_e2e_customers,
    ensure_e2e_analysts,
    export_bundle,
    prepare_app_e2e,
    run_analyst,
    run_reception,
    run_reviewer,
    run_scenario,
    _water_input_order,
)
from services.protocol_store import list_results
from services.samples import get_by_code

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.integration


@pytest.fixture
def e2e_analysts(require_db):
    prepare_app_e2e()
    return ensure_e2e_analysts()


def test_water_app_flow_end_to_end(require_db, e2e_analysts, tmp_path):
    """Water scenario through DB: reception, analyst results, reviewer report."""
    chem_id, micro_id = e2e_analysts
    scenarios = build_demo_scenarios(chem_id, micro_id)
    water = next(s for s in scenarios if s.label == "01_water_abc_foods")

    cleanup_e2e_customers([water.customer.gst_number])
    sample_code = run_reception(water)
    assert sample_code

    run_analyst(
        sample_code,
        water,
        chem_analyst_id=chem_id,
        micro_analyst_id=micro_id,
    )
    sample = get_by_code(sample_code)
    assert sample is not None
    results = list_results(sample.id)
    assert len(results) >= len(_water_input_order())

    report = run_reviewer(sample_code, water)
    assert report.docx_bytes
    assert report.is_water

    export_bundle(
        label=water.label,
        sample_code=sample_code,
        report_output=report,
        out_dir=tmp_path,
        project_root=PROJECT_ROOT,
        scenario=water,
    )

    doc = Document(io.BytesIO(report.docx_bytes))
    assert len(doc.sections) == 2
    micro_table = doc.tables[4]
    assert "Absent" in micro_table.rows[2].cells[2].text

    reported = get_by_code(sample_code)
    assert reported is not None
    assert reported.status == "reported"

    cleanup_e2e_customers([water.customer.gst_number])


def test_run_scenario_water(require_db, e2e_analysts, tmp_path):
    chem_id, micro_id = e2e_analysts
    water = build_demo_scenarios(chem_id, micro_id)[0]
    code = run_scenario(
        water,
        tmp_path,
        PROJECT_ROOT,
        chem_analyst_id=chem_id,
        micro_analyst_id=micro_id,
    )
    assert code
    cleanup_e2e_customers([water.customer.gst_number])
