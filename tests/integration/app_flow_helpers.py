"""
App-flow integration helpers: same services as Reception / Analyst / Reviewer pages.

Not used by pytest e2e demo scenarios (services/e2e_app_flow.py).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from services.ctr_pdf import generate_ctr_documents
from services.docx_to_pdf import format_word_conversion_error
from services.protocol_store import (
    ProtocolHeader,
    get_protocol_header,
    list_results,
    save_test_result,
    upsert_protocol_header,
)
from services.protocol_pdf import generate_protocol_documents
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    normalize_category,
)
from services.report_settings import default_authorized_signatory, load_report_settings
from services.requests import (
    SampleRow,
    TestRequestData,
    get_test_request,
    save_test_request,
    storage_temperature_for_save,
)
from services.reviewer_report import (
    ReviewerGenerationParams,
    build_generation_params,
    generate_reviewer_final_report,
)
from services.samples import SampleRecord, get_by_code, update_status
from services.test_report_pdf import FinalReportOutput
from services.ulr import generate_ulr_no, lab_code_for_ulr
from tests.conftest import sample_verification_kwargs
from tests.integration.dummy_document_helpers import dummy_customer

APP_FLOW_PREVIEW_ROOT = (
    Path(__file__).resolve().parent.parent / "output_preview" / "app_flow"
)

APP_FLOW_LAB = "SLS/26/901"
APP_FLOW_PROTOCOL_NO = "P-APP-001"
APP_FLOW_CUSTOMER_NAME = "App Flow Test Customer Pvt Ltd"
GENERATED_BY = "App Flow Integration Test"
GENERATED_AT = "21/07/2026 12:00"
_ANALYSIS_DATE = date(2026, 7, 22)
_RECEIVED_DATE = date(2026, 7, 21)
_REQUEST_DATE = date(2026, 7, 21)


def ensure_app_flow_dirs(category: str) -> dict[str, Path]:
    """Create ctr / protocol / final_report dirs for a category."""
    base = APP_FLOW_PREVIEW_ROOT / category
    out = {
        "ctr": base / "ctr",
        "protocol": base / "protocol",
        "final_report": base / "final_report",
    }
    for path in out.values():
        path.mkdir(parents=True, exist_ok=True)
    return out


def _verification() -> dict:
    return sample_verification_kwargs(verify_lab_code=APP_FLOW_LAB)


def _food_moisture_inputs() -> dict[str, dict[str, Any]]:
    return {
        "moisture": {
            "empty_dish": "50.0",
            "w1": "55.0",
            "w": "5.0",
            "w2": "54.8235",
        },
    }


def _water_ph_inputs() -> dict[str, dict[str, Any]]:
    return {"ph": {"ph_value": "7.320"}}


def _micro_inputs() -> dict[str, dict[str, Any]]:
    keys = ["total_plate_count", "e_coli"]
    all_inputs = {
        "total_plate_count": {"result_value": "3.0 x 10³ cfu/gm"},
        "t_coliform": {"result_value": "Absent"},
        "e_coli": {"result_value": "Absent"},
        "salmonella": {"result_value": "Absent"},
        "staphylococcus_aureus": {"result_value": "Absent"},
        "yeast_and_mould": {"result_value": "< 10 cfu/gm"},
    }
    return {k: all_inputs[k] for k in keys}


def analyst_inputs_for_category(category: str) -> dict[str, dict[str, Any]]:
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        return _water_ph_inputs()
    if cat == CATEGORY_MICRO:
        return _micro_inputs()
    return _food_moisture_inputs()


def category_sample_row(
    category: str,
    chem_analyst_id: int,
    micro_analyst_id: int,
) -> SampleRow:
    verify = _verification()
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        return SampleRow(
            sr_no=1,
            sample_name="App Flow Potable Water",
            batch_code="---",
            quantity="1 lit",
            parameters="Drinking Water",
            category=CATEGORY_WATER,
            test_keys=["ph"],
            assigned_analyst_id=chem_analyst_id,
            assigned_micro_analyst_id=micro_analyst_id,
            protocol_no=APP_FLOW_PROTOCOL_NO,
            storage_temperature=storage_temperature_for_save("4°C", ""),
            **verify,
        )
    if cat == CATEGORY_MICRO:
        micro_keys = ["total_plate_count", "e_coli"]
        return SampleRow(
            sr_no=1,
            sample_name="App Flow Paneer Gravy",
            quantity="250 gm",
            parameters="Cooked food",
            category=CATEGORY_MICRO,
            test_keys=micro_keys,
            assigned_analyst_id=chem_analyst_id,
            protocol_no=APP_FLOW_PROTOCOL_NO,
            storage_temperature=storage_temperature_for_save("2°C to 8°C", ""),
            **verify,
        )
    return SampleRow(
        sr_no=1,
        sample_name="App Flow Jaggery",
        batch_code="B-APP-01",
        quantity="500 g",
        parameters="FSSAI",
        parameters_select="FSSAI",
        package_type="fssai",
        category=CATEGORY_FOOD,
        test_keys=["moisture"],
        tests_with_logo=["moisture"],
        report_format="with_logo",
        assigned_analyst_id=chem_analyst_id,
        protocol_no=APP_FLOW_PROTOCOL_NO,
        storage_temperature=storage_temperature_for_save("Room Temp", ""),
        **verify,
    )


def _ctr_test_request(gst: str, sample: SampleRow) -> TestRequestData:
    return TestRequestData(
        customer=dummy_customer(gst, name=APP_FLOW_CUSTOMER_NAME),
        request_date=_REQUEST_DATE,
        lab_code=APP_FLOW_LAB,
        number_of_samples=1,
        sampling_by_lab=True,
        storage_temperature="4°C",
        decision_rule=True,
        service_type="regular",
        delivery_mode="Collect",
        samples=[sample],
    )


def save_reception_request(gst: str, sample: SampleRow) -> TestRequestData:
    saved = save_test_request(_ctr_test_request(gst, sample), actor=None)
    loaded = get_test_request(saved.request_id)
    if loaded is None:
        raise RuntimeError("save_test_request did not persist request")
    return loaded


def seed_analyst_work(
    sample: SampleRecord,
    category: str,
    inputs_by_key: dict[str, dict[str, Any]],
    *,
    appearance: str = "Normal",
) -> None:
    upsert_protocol_header(
        ProtocolHeader(
            sample_id=sample.id,
            protocol_no=APP_FLOW_PROTOCOL_NO,
            issued_to="QA Analyst",
            issued_by="Reception",
            sample_received_on=_RECEIVED_DATE,
            date_of_analysis=_ANALYSIS_DATE,
            appearance_text=appearance,
        ),
        actor=None,
    )
    for test_key, inputs in inputs_by_key.items():
        save_test_result(sample.id, test_key, inputs, actor=None)
    code = (sample.sample_code or "").strip()
    if not code:
        raise RuntimeError("sample missing sample_code")
    update_status(code, "completed", "App flow analyst complete", actor=None)


def _safe_filename(name: str) -> str:
    return name.replace("/", "-").replace("\\", "-")


def write_bundle_files(
    out_dir: Path,
    docx_filename: str,
    docx_bytes: bytes,
    pdf_bytes: bytes | None,
    pdf_filename: str | None = None,
) -> tuple[Path, Path]:
    """Write DOCX and PDF; returns (docx_path, pdf_path)."""
    docx_path = out_dir / _safe_filename(docx_filename)
    docx_path.write_bytes(docx_bytes)
    if pdf_bytes is None:
        raise ValueError("pdf_bytes required")
    if pdf_filename:
        pdf_name = _safe_filename(pdf_filename)
    else:
        pdf_name = docx_path.stem + ".pdf"
    pdf_path = out_dir / pdf_name
    pdf_path.write_bytes(pdf_bytes)
    return docx_path, pdf_path


def require_pdf(
    pdf_bytes: bytes | None,
    pdf_error: str | None,
    label: str,
) -> bytes:
    if pdf_bytes is not None and pdf_bytes[:4] == b"%PDF":
        return pdf_bytes
    detail = format_word_conversion_error(pdf_error) if pdf_error else "no PDF bytes"
    pytest.fail(
        f"{label} PDF required (install Microsoft Word or LibreOffice): {detail}"
    )


def _appearance_for_category(category: str) -> str:
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        return "Colorless transparent liquid"
    if cat == CATEGORY_MICRO:
        return "Reddish orange coloured gravy."
    return "Brown colored solid jaggery."


def _reviewer_field_map(
    sample: SampleRecord,
    header: ProtocolHeader,
    request: TestRequestData,
) -> dict[str, Any]:
    settings = load_report_settings()
    auth = default_authorized_signatory(settings)
    code = sample.sample_code or ""
    cat = normalize_category(sample.category)
    customer_block = (
        f"{request.customer.customer_name or ''}\n{request.customer.address or ''}".strip()
    )
    fields: dict[str, Any] = {
        "auth_signatory": auth,
        "checked_by": "QA Analyst",
        "condition": "Sealed sample container",
        "appearance": header.appearance_text or _appearance_for_category(cat),
        "customer_sid": sample.sample_name or "",
    }
    if cat == CATEGORY_WATER:
        ulr = generate_ulr_no(lab_code_for_ulr(sample.lab_code, sample.sample_code))
        fields.update(
            {
                "ulr": ulr,
                "report_chem": f"W-CHEM-{code[-6:]}",
                "report_micro": f"W-MIC-{code[-6:]}",
                "testing_at": "Surendra Testing Laboratory",
            }
        )
    elif cat == CATEGORY_MICRO:
        fields["report_no"] = f"M-RPT-{code[-6:]}"
    else:
        fields.update(
            {
                "report_date": _ANALYSIS_DATE.isoformat(),
                "customer_addr": customer_block,
                "batch_no": sample.batch_code or "B-APP-01",
                "lab_code": sample.lab_code or APP_FLOW_LAB,
                "tests_processed": "FSSAI panel",
                "location": "Client site",
                "sampling_method": "Random",
                "remark": "App flow integration test",
                "disclaimer": "Report valid for submitted sample only.",
            }
        )
    return fields


def generate_reviewer_report(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list,
    request: TestRequestData,
) -> FinalReportOutput:
    cat = normalize_category(sample.category)
    is_water = cat == CATEGORY_WATER
    is_micro = cat == CATEGORY_MICRO
    field_map = _reviewer_field_map(sample, header, request)

    def get_field(key: str, sample_code: str) -> Any:
        if sample_code != (sample.sample_code or ""):
            return ""
        return field_map.get(key, "")

    params: ReviewerGenerationParams = build_generation_params(
        sample,
        is_water=is_water,
        is_micro=is_micro,
        specs_df=None,
        sample_code=sample.sample_code or "",
        report_settings=load_report_settings(),
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        get_field=get_field,
    )
    output = generate_reviewer_final_report(sample, header, results, params)
    code = (sample.sample_code or "").strip()
    update_status(
        code,
        "reported",
        "[App flow test] Final report generated",
        actor=None,
    )
    return output


def run_app_flow_for_category(
    gst: str,
    category: str,
    chem_analyst_id: int,
    micro_analyst_id: int,
) -> dict[str, tuple[Path, Path]]:
    """Reception → Analyst → Reviewer document generation; returns written paths."""
    dirs = ensure_app_flow_dirs(category)
    sample_row = category_sample_row(category, chem_analyst_id, micro_analyst_id)
    request_data = save_reception_request(gst, sample_row)

    ctr_docx, ctr_pdf, ctr_docx_name, ctr_pdf_name, ctr_err = generate_ctr_documents(
        request_data,
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
    )
    ctr_pdf = require_pdf(ctr_pdf, ctr_err, "CTR")
    ctr_paths = write_bundle_files(
        dirs["ctr"], ctr_docx_name, ctr_docx, ctr_pdf, ctr_pdf_name
    )

    sample_code = request_data.samples[0].sample_code
    assert sample_code
    row = get_by_code(sample_code)
    assert row is not None
    inputs = analyst_inputs_for_category(category)
    seed_analyst_work(
        row,
        category,
        inputs,
        appearance=_appearance_for_category(category),
    )

    row = get_by_code(sample_code)
    assert row is not None
    header = get_protocol_header(row.id)
    assert header is not None
    results = list_results(row.id)
    assert results

    p_docx, p_pdf, p_docx_name, p_pdf_name, p_err = generate_protocol_documents(
        row,
        header,
        results,
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
    )
    p_pdf = require_pdf(p_pdf, p_err, "Protocol")
    proto_paths = write_bundle_files(
        dirs["protocol"], p_docx_name, p_docx, p_pdf, p_pdf_name
    )

    row = get_by_code(sample_code)
    assert row is not None
    header = get_protocol_header(row.id)
    assert header is not None
    results = list_results(row.id)
    final = generate_reviewer_report(row, header, results, request_data)
    require_pdf(final.pdf_bytes, None, "Final report")
    assert final.docx_bytes
    final_paths = write_bundle_files(
        dirs["final_report"],
        final.docx_filename or f"FinalReport_{category}.docx",
        final.docx_bytes,
        final.pdf_bytes,
        final.pdf_filename,
    )

    return {
        "ctr": ctr_paths,
        "protocol": proto_paths,
        "final_report": final_paths,
    }
