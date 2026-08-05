"""
Generate sample protocol and final report documents for water, micro, and food.

Uses reference templates in reference/ and writes output to tmp/generated_samples/.
Run from project root: python scripts/generate_sample_documents.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.protocol_docx import JAGGERY_TEMPLATE_PATH, fill_protocol_docx_bytes
from services.protocol_pdf import generate_protocol_documents
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import (
    MICRO_TEST_KEYS,
    NUTRITION_TEST_KEYS,
    TEST_CATALOG,
    WATER_TEST_KEYS,
    get_test,
)
from services.samples import SampleRecord
from services.test_report_micro_docx import MicroReportFillOptions
from services.test_report_pdf import generate_final_report
from services.test_report_water_docx import WaterReportFillOptions

OUTPUT_DIR = PROJECT_ROOT / "tmp" / "generated_samples"
GENERATED_BY = "S_LAB Demo"
GENERATED_AT = "04/08/2026 17:30"


def _result_row(
    test_key: str,
    result_value: str,
    *,
    result_numeric: float | None = None,
    inputs: dict | None = None,
) -> TestResultRow:
    test = get_test(test_key)
    return TestResultRow(
        test_key=test_key,
        test_name=test.name,
        method=test.method,
        unit=test.unit,
        inputs=inputs or {},
        result_value=result_value,
        result_numeric=result_numeric,
    )


def _header(sample_id: int, **overrides) -> ProtocolHeader:
    base = dict(
        sample_id=sample_id,
        protocol_no="P-DEMO-001",
        issued_to="Analyst Demo",
        issued_by="Reception Demo",
        sample_received_on=date(2026, 7, 27),
        date_of_analysis=date(2026, 7, 30),
        appearance_text="",
    )
    base.update(overrides)
    return ProtocolHeader(**base)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  wrote {path.relative_to(PROJECT_ROOT)} ({len(data):,} bytes)")


def _water_results() -> list[TestResultRow]:
    return [
        _result_row("ph", "7.320", result_numeric=7.32, inputs={"ph_value": "7.320"}),
        _result_row("tds", "185", result_numeric=185.0),
        _result_row("chlorides", "42.5", result_numeric=42.5),
        _result_row("total_alkalinity", "95.0", result_numeric=95.0),
        _result_row("conductivity", "285", result_numeric=285.0),
        _result_row("total_hardness", "120", result_numeric=120.0),
        _result_row("calcium_ca", "28.5", result_numeric=28.5),
        _result_row("calcium_caco3", "71.2", result_numeric=71.2),
        _result_row("magnesium", "11.8", result_numeric=11.8),
        _result_row("odor", "Agreeable", inputs={"odor_obs": "Agreeable"}),
        _result_row("turbidity", "0.8", result_numeric=0.8),
    ]


def _micro_results() -> list[TestResultRow]:
    values = {
        "total_plate_count": "3.0 x 10³ cfu/gm",
        "t_coliform": "Absent",
        "e_coli": "Absent",
        "salmonella": "Absent",
        "staphylococcus_aureus": "Absent",
        "yeast_and_mould": "< 10 cfu/gm",
    }
    rows = []
    for key in MICRO_TEST_KEYS:
        val = values[key]
        rows.append(
            _result_row(
                key,
                val,
                inputs={"result_obs": val},
            )
        )
    return rows


def _nutrition_results() -> list[TestResultRow]:
    return [
        _result_row("appearance", "Brown granular powder", inputs={"appearance_obs": "Brown granular powder"}),
        _result_row("bn_moisture", "4.2", result_numeric=4.2),
        _result_row("bn_total_ash", "1.8", result_numeric=1.8),
        _result_row("bn_total_fat", "0.5", result_numeric=0.5),
        _result_row("bn_protein", "12.4", result_numeric=12.4),
        _result_row("bn_carbohydrate", "78.6", result_numeric=78.6),
        _result_row("bn_calories", "368", result_numeric=368.0),
        _result_row("bn_crude_fibre", "2.1", result_numeric=2.1),
        _result_row("bn_added_sugar", "0.0", result_numeric=0.0),
        _result_row("bn_total_sugar", "65.2", result_numeric=65.2),
    ]


def generate_water(out: Path) -> None:
    print("\n[Water]")
    sample = SampleRecord(
        id=1,
        request_id=1,
        sample_code="SLS-260727-0001",
        sr_no=1,
        sample_name="Potable Water",
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
        tests_to_perform="",
        status="completed",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="water",
        tests_json=json.dumps(WATER_TEST_KEYS),
        lab_code="SLS/26/638/01",
        customer_name="ABC Foods Pvt Ltd",
        customer_address="Nashik, Maharashtra",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    header = _header(
        1,
        protocol_no="P-W-2026-001",
        appearance_text="Colorless transparent liquid",
    )
    results = _water_results()

    docx_bytes, pdf_bytes, docx_name, pdf_name, _pdf_err = generate_protocol_documents(
        sample, header, results, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(out / "protocol" / docx_name, docx_bytes)
    if pdf_bytes:
        _write(out / "protocol" / pdf_name, pdf_bytes)

    water_opts = WaterReportFillOptions(
        ulr_no="TC-1234567890",
        report_no_chemical="SLS/26/638/01/01",
        report_no_micro="SLS/26/638/01/02",
        report_date=date(2026, 7, 30),
        condition_of_sample="Packed in plastic container",
        customer_sample_id="Drinking Water",
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
    )
    report = generate_final_report(
        sample,
        header,
        results,
        report_date=date(2026, 7, 30),
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        condition_of_sample="Packed in plastic container",
        water_opts=water_opts,
    )
    _write(out / "report" / report.docx_filename, report.docx_bytes)
    if report.pdf_bytes:
        _write(out / "report" / report.pdf_filename, report.pdf_bytes)


def generate_micro(out: Path) -> None:
    print("\n[Micro] (no analyst protocol — final report only)")
    sample = SampleRecord(
        id=2,
        request_id=2,
        sample_code="SLS-260704-0001",
        sr_no=1,
        sample_name="Cooked Food: Paneer Gravy",
        batch_code="",
        quantity="250 gm",
        parameters="Paneer Gravy",
        tests_to_perform="",
        status="completed",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="micro",
        tests_json=json.dumps(MICRO_TEST_KEYS),
        lab_code="SLS/26/546/03",
        customer_name="XYZ Caterers",
        customer_address="Pune, Maharashtra",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
        sampling_by_lab=False,
    )
    header = _header(
        2,
        protocol_no="P-M-2026-001",
        appearance_text="Reddish orange coloured Paneer gravy.",
    )
    results = _micro_results()

    micro_opts = MicroReportFillOptions(
        report_no="SLS/26/546/03/01",
        report_date=date(2026, 7, 9),
        condition_of_sample="Company packing",
        customer_sample_id="Paneer Gravy",
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
    )
    report = generate_final_report(
        sample,
        header,
        results,
        report_date=date(2026, 7, 9),
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        condition_of_sample="Company packing",
        micro_opts=micro_opts,
    )
    _write(out / "report" / report.docx_filename, report.docx_bytes)
    if report.pdf_bytes:
        _write(out / "report" / report.pdf_filename, report.pdf_bytes)


def generate_food(out: Path) -> None:
    print("\n[Food — Basic Nutrition]")
    nutrition_keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    sample = SampleRecord(
        id=3,
        request_id=3,
        sample_code="SLS-260730-0001",
        sr_no=1,
        sample_name="Protein Supplement Mix",
        batch_code="BN-2026-07",
        quantity="500 g",
        parameters="",
        tests_to_perform="",
        status="completed",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        package_type="basic_nutrition",
        tests_json=json.dumps(nutrition_keys),
        lab_code="SLS/26/701/01",
        customer_name="NutriHealth Foods",
        customer_address="Mumbai, Maharashtra",
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    header = _header(
        3,
        protocol_no="P-F-2026-001",
        appearance_text="Brown granular powder",
    )
    results = _nutrition_results()

    docx_bytes, pdf_bytes, docx_name, pdf_name, _pdf_err = generate_protocol_documents(
        sample, header, results, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(out / "protocol" / docx_name, docx_bytes)
    if pdf_bytes:
        _write(out / "protocol" / pdf_name, pdf_bytes)

    report = generate_final_report(
        sample,
        header,
        results,
        report_date=date(2026, 7, 30),
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        condition_of_sample="Sealed poly pouch",
    )
    if report.pdf_bytes:
        _write(out / "report" / report.pdf_filename, report.pdf_bytes)
    elif report.docx_bytes:
        _write(out / "report" / report.docx_filename, report.docx_bytes)


def main() -> None:
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Templates: Water={ (PROJECT_ROOT / 'reference' / 'Water protocol 2025.docx').exists() }")
    print(f"           Nutrition={ (PROJECT_ROOT / 'reference' / 'Basic Nutrition Protocol 2026.docx').exists() }")
    print(f"           Water report={ (PROJECT_ROOT / 'reference' / 'Water test report.docx').exists() }")
    if not JAGGERY_TEMPLATE_PATH.exists():
        print("Note: Jaggery (FSSAI) protocol template missing — using Basic Nutrition for food.")

    generate_water(OUTPUT_DIR / "water")
    generate_micro(OUTPUT_DIR / "micro")
    generate_food(OUTPUT_DIR / "food")

    print("\nDone. Open files under tmp/generated_samples/")


if __name__ == "__main__":
    main()
