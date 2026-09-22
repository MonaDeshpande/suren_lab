"""
Dummy CTR + water/food/micro protocol generation through app services, with DB cleanup.

Run (Postgres required):
  pytest tests/integration/test_dummy_document_generation.py -v -s

Artifacts: tests/output_preview/integration/{ctr,water,food,micro}/
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from services.ctr_pdf import generate_ctr_documents
from services.e2e_app_flow import _micro_analyst_inputs, _water_analyst_inputs
from services.protocol_pdf import generate_protocol_documents
from services.protocol_store import (
    ProtocolHeader,
    get_protocol_header,
    list_results,
    save_test_result,
    upsert_protocol_header,
)
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    TEST_CATALOG,
)
from services.requests import (
    SampleRow,
    TestRequestData,
    get_test_request,
    save_test_request,
    storage_temperature_for_save,
)
from services.samples import get_by_code
from tests.conftest import cleanup_test_data, sample_verification_kwargs
from tests.integration.dummy_document_helpers import (
    assert_db_clean_for_gst,
    docx_body_text,
    dummy_customer,
    ensure_integration_preview_dirs,
    write_preview_bytes,
    write_protocol_preview,
)
from tests.test_report_preview import _assert_ctr_content

pytestmark = pytest.mark.integration

_DUMMY_LAB = "LAB/PY/26/001"
_PROTOCOL_NO = "P-DUMMY-001"
_CTR_CUSTOMER = "Pytest Dummy Customer Pvt Ltd"


@pytest.fixture(scope="session")
def integration_preview_dirs() -> dict[str, Path]:
    return ensure_integration_preview_dirs()


def _verification() -> dict:
    return sample_verification_kwargs(verify_lab_code=_DUMMY_LAB)


def _ctr_test_request(gst: str, sample: SampleRow) -> TestRequestData:
    return TestRequestData(
        customer=dummy_customer(gst, name=_CTR_CUSTOMER),
        request_date=date(2026, 7, 21),
        lab_code=_DUMMY_LAB,
        number_of_samples=1,
        sampling_by_lab=True,
        storage_temperature="4°C",
        decision_rule=True,
        service_type="regular",
        delivery_mode="Collect",
        samples=[sample],
    )


def _save_and_load_request(gst: str, sample: SampleRow):
    saved = save_test_request(_ctr_test_request(gst, sample), actor=None)
    loaded = get_test_request(saved.request_id)
    assert loaded is not None
    return loaded


def _seed_protocol(
    sample_id: int,
    *,
    appearance: str,
    inputs_by_key: dict[str, dict],
) -> None:
    upsert_protocol_header(
        ProtocolHeader(
            sample_id=sample_id,
            protocol_no=_PROTOCOL_NO,
            issued_to="QA Analyst",
            issued_by="Reception",
            sample_received_on=date(2026, 7, 21),
            date_of_analysis=date(2026, 7, 22),
            appearance_text=appearance,
        ),
        actor=None,
    )
    for test_key, inputs in inputs_by_key.items():
        save_test_result(sample_id, test_key, inputs, actor=None)


def test_dummy_ctr_generates_pdf_and_docx(
    require_db,
    qa_analyst_pair,
    db_test_gst,
    integration_preview_dirs,
):
    """Save one dummy sample, generate CTR PDF/DOCX, write preview, wipe DB."""
    chem, micro = qa_analyst_pair
    verify = _verification()
    sample = SampleRow(
        sr_no=1,
        sample_name="Dummy CTR Water Sample",
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
        category=CATEGORY_WATER,
        test_keys=["ph"],
        assigned_analyst_id=chem.id,
        assigned_micro_analyst_id=micro.id,
        protocol_no=_PROTOCOL_NO,
        storage_temperature=storage_temperature_for_save("4°C", ""),
        **verify,
    )
    out_dir = integration_preview_dirs["ctr"]
    try:
        loaded = _save_and_load_request(db_test_gst, sample)
        (
            docx_bytes,
            pdf_bytes,
            docx_name,
            pdf_name,
            pdf_error,
        ) = generate_ctr_documents(
            loaded,
            generated_by="Integration Test",
            generated_at="21/07/2026 12:00",
        )
        if pdf_bytes is None:
            pytest.fail(
                f"CTR PDF required for integration test: {pdf_error or 'no PDF'}"
            )
        _assert_ctr_content(pdf_bytes, docx_bytes, customer_name=_CTR_CUSTOMER)
        assert "Dummy CTR Water Sample" in docx_body_text(docx_bytes)

        pdf_path = write_preview_bytes(out_dir, pdf_name, pdf_bytes)
        docx_path = write_preview_bytes(out_dir, docx_name, docx_bytes)
        print(f"\nCTR preview:\n  {pdf_path}\n  {docx_path}")
    finally:
        cleanup_test_data(gst=db_test_gst)
    assert_db_clean_for_gst(db_test_gst)


def test_dummy_protocol_water_generates_and_wipes(
    require_db,
    qa_analyst_pair,
    db_test_gst,
    integration_preview_dirs,
):
    chem, micro = qa_analyst_pair
    verify = _verification()
    water_inputs = _water_analyst_inputs()
    sample = SampleRow(
        sr_no=1,
        sample_name="Dummy Potable Water",
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
        category=CATEGORY_WATER,
        test_keys=["ph"],
        assigned_analyst_id=chem.id,
        assigned_micro_analyst_id=micro.id,
        protocol_no=_PROTOCOL_NO,
        storage_temperature=storage_temperature_for_save("4°C", ""),
        **verify,
    )
    out_dir = integration_preview_dirs["water"]
    try:
        sample_code = _save_and_load_request(db_test_gst, sample).samples[0].sample_code
        assert sample_code
        row = get_by_code(sample_code)
        assert row is not None
        _seed_protocol(row.id, appearance="Clear", inputs_by_key={"ph": water_inputs["ph"]})

        header = get_protocol_header(row.id)
        assert header is not None
        results = list_results(row.id)
        docx_bytes, pdf_bytes, docx_name, _, _ = generate_protocol_documents(
            row, header, results
        )
        assert len(docx_bytes) > 5000
        text = docx_body_text(docx_bytes)
        assert _PROTOCOL_NO in text
        assert "system" not in text.lower()
        assert "Sample Issued" in text

        docx_path, pdf_path = write_protocol_preview(
            out_dir,
            docx_filename=docx_name,
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
        )
        print(f"\nWater protocol preview:\n  {docx_path}")
        if pdf_path:
            print(f"  {pdf_path}")
    finally:
        cleanup_test_data(gst=db_test_gst)
    assert_db_clean_for_gst(db_test_gst)


def test_dummy_protocol_food_generates_and_wipes(
    require_db,
    qa_analyst_pair,
    db_test_gst,
    integration_preview_dirs,
):
    chem, _micro = qa_analyst_pair
    verify = _verification()
    sample = SampleRow(
        sr_no=1,
        sample_name="Dummy Jaggery",
        batch_code="B-01",
        quantity="500 g",
        parameters="FSSAI",
        parameters_select="FSSAI",
        package_type="fssai",
        category=CATEGORY_FOOD,
        test_keys=["moisture"],
        tests_with_logo=["moisture"],
        report_format="with_logo",
        assigned_analyst_id=chem.id,
        protocol_no=_PROTOCOL_NO,
        storage_temperature=storage_temperature_for_save("Room Temp", ""),
        **verify,
    )
    moisture_inputs = {
        "empty_dish": "50.0",
        "w1": "55.0",
        "w": "5.0",
        "w2": "54.8235",
    }
    out_dir = integration_preview_dirs["food"]
    try:
        sample_code = _save_and_load_request(db_test_gst, sample).samples[0].sample_code
        assert sample_code
        row = get_by_code(sample_code)
        assert row is not None
        _seed_protocol(
            row.id,
            appearance="Brown colored solid jaggery.",
            inputs_by_key={"moisture": moisture_inputs},
        )

        header = get_protocol_header(row.id)
        assert header is not None
        results = list_results(row.id)
        docx_bytes, pdf_bytes, docx_name, _, _ = generate_protocol_documents(
            row, header, results
        )
        assert len(docx_bytes) > 5000
        text = docx_body_text(docx_bytes)
        assert "Dummy Jaggery" in text
        assert "3.53" in text or "3.5" in text

        docx_path, pdf_path = write_protocol_preview(
            out_dir,
            docx_filename=docx_name,
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
        )
        print(f"\nFood protocol preview:\n  {docx_path}")
        if pdf_path:
            print(f"  {pdf_path}")
    finally:
        cleanup_test_data(gst=db_test_gst)
    assert_db_clean_for_gst(db_test_gst)


def test_dummy_protocol_micro_generates_and_wipes(
    require_db,
    qa_analyst_pair,
    db_test_gst,
    integration_preview_dirs,
):
    chem, _micro = qa_analyst_pair
    verify = _verification()
    micro_keys = ["total_plate_count", "e_coli"]
    all_micro_inputs = _micro_analyst_inputs()
    sample = SampleRow(
        sr_no=1,
        sample_name="Dummy Paneer Gravy",
        quantity="250 gm",
        parameters="Cooked food",
        category=CATEGORY_MICRO,
        test_keys=micro_keys,
        assigned_analyst_id=chem.id,
        protocol_no=_PROTOCOL_NO,
        storage_temperature=storage_temperature_for_save("2°C to 8°C", ""),
        **verify,
    )
    out_dir = integration_preview_dirs["micro"]
    try:
        sample_code = _save_and_load_request(db_test_gst, sample).samples[0].sample_code
        assert sample_code
        row = get_by_code(sample_code)
        assert row is not None
        _seed_protocol(
            row.id,
            appearance="Normal",
            inputs_by_key={k: all_micro_inputs[k] for k in micro_keys},
        )

        header = get_protocol_header(row.id)
        assert header is not None
        results = list_results(row.id)
        docx_bytes, pdf_bytes, docx_name, _, _ = generate_protocol_documents(
            row, header, results
        )
        assert len(docx_bytes) > 5000
        text = docx_body_text(docx_bytes)
        assert TEST_CATALOG["total_plate_count"].name in text

        docx_path, pdf_path = write_protocol_preview(
            out_dir,
            docx_filename=docx_name,
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
        )
        print(f"\nMicro protocol preview:\n  {docx_path}")
        if pdf_path:
            print(f"  {pdf_path}")
    finally:
        cleanup_test_data(gst=db_test_gst)
    assert_db_clean_for_gst(db_test_gst)
