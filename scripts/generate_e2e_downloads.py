"""
End-to-end document bundle: CTR + protocol + final test report for Food, Water, Micro.

Default mode runs Reception -> Analyst -> Reviewer through PostgreSQL (same services
as the Streamlit app). Use --offline for the legacy in-memory demo path.

Run from project root: python scripts/generate_e2e_downloads.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.customers import Customer
from services.docx_filler import fill_docx_bytes, suggest_docx_filename
from services.micro_protocol_docx import (
    fill_micro_protocol_docx_bytes,
    suggest_micro_protocol_filename,
)
from services.pdf_generator import generate_pdf_bytes, suggest_pdf_filename
from services.protocol_pdf import generate_protocol_documents
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import (
    JAGGERY_TEST_KEYS,
    MICRO_TEST_KEYS,
    NUTRITION_TEST_KEYS,
    WATER_TEST_KEYS,
    get_test,
)
from services.requests import SampleRow, TestRequestData
from services.samples import SampleRecord, derive_sample_code
from services.test_report_pdf import generate_final_report

OUTPUT_ROOT = PROJECT_ROOT / "downloads" / "e2e_demo"
GENERATED_BY = "S_LAB E2E"
GENERATED_AT = "24/08/2026 15:00"


def _verification(lab_code: str) -> dict:
    return {
        "verify_review_date": date(2026, 7, 27),
        "verify_lab_code": lab_code,
        "verify_sample_condition": "Ambient",
        "verify_qty_checked": True,
        "verify_chemical_available": True,
        "verify_methods_available": True,
        "verify_methods_informed": True,
        "verify_tat_informed": True,
        "verify_ready_to_issue": True,
        "verify_conformity_statement": False,
    }


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


def _safe_filename(name: str) -> str:
    return name.replace("/", "-").replace("\\", "-")


def _write(path: Path, data: bytes) -> None:
    path = path.parent / _safe_filename(path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  wrote {path.relative_to(PROJECT_ROOT)} ({len(data):,} bytes)")


def _ctr_request(
    *,
    customer: Customer,
    lab_code: str,
    sample: SampleRow,
    request_date: date,
) -> TestRequestData:
    return TestRequestData(
        customer=customer,
        request_date=request_date,
        lab_code=lab_code,
        number_of_samples=1,
        sampling_by_lab=True,
        storage_temperature="4°C",
        decision_rule=True,
        service_type="regular",
        delivery_mode="Collect, Email/Whatsapp",
        samples=[sample],
    )


def _sample_record(
    *,
    sample_id: int,
    request_id: int,
    lab_code: str,
    category: str,
    sample_name: str,
    tests_json: list[str],
    customer_name: str,
    customer_address: str,
    **extra,
) -> SampleRecord:
    code = derive_sample_code(lab_code, index=1, total=1)
    base = dict(
        id=sample_id,
        request_id=request_id,
        sample_code=code,
        sr_no=1,
        sample_name=sample_name,
        batch_code="",
        quantity="",
        parameters="",
        tests_to_perform="",
        status="completed",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category=category,
        tests_json=json.dumps(tests_json),
        lab_code=lab_code,
        customer_name=customer_name,
        customer_address=customer_address,
        report_format="with_logo",
        tests_with_logo_json="",
        tests_without_logo_json="",
    )
    base.update(extra)
    return SampleRecord(**base)


def _water_results() -> list[TestResultRow]:
    return [
        _result_row("ph", "7.320", result_numeric=7.32),
        _result_row("tds", "185", result_numeric=185.0),
        _result_row("chlorides", "42.5", result_numeric=42.5),
        _result_row("total_alkalinity", "95.0", result_numeric=95.0),
        _result_row("conductivity", "285", result_numeric=285.0),
        _result_row("total_hardness", "120", result_numeric=120.0),
        _result_row("calcium_ca", "28.5", result_numeric=28.5),
        _result_row("calcium_caco3", "71.2", result_numeric=71.2),
        _result_row("magnesium", "11.8", result_numeric=11.8),
        _result_row("odor", "Agreeable"),
        _result_row("turbidity", "0.8", result_numeric=0.8),
        _result_row(
            "water_total_coliform",
            "absent",
            inputs={"result_obs": "absent"},
        ),
        _result_row(
            "water_e_coli",
            "absent",
            inputs={"result_obs": "absent"},
        ),
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
    return [
        _result_row(key, val, inputs={"result_obs": val})
        for key in MICRO_TEST_KEYS
        for val in [values[key]]
    ]


def _nutrition_results() -> list[TestResultRow]:
    nutrition_keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    values = {
        "appearance": "Brown granular powder",
        "bn_moisture": "4.2",
        "bn_total_ash": "1.8",
        "bn_total_fat": "0.5",
        "bn_protein": "12.4",
        "bn_carbohydrate": "78.6",
        "bn_calories": "368",
        "bn_crude_fibre": "2.1",
        "bn_added_sugar": "0.0",
        "bn_total_sugar": "65.2",
    }
    rows = []
    for key in nutrition_keys:
        val = values.get(key, "")
        num = None
        try:
            num = float(val)
        except ValueError:
            pass
        rows.append(
            _result_row(
                key,
                val,
                result_numeric=num,
                inputs={"appearance_obs": val} if key == "appearance" else {},
            )
        )
    return rows


def generate_client_bundle(
    out_dir: Path,
    *,
    label: str,
    ctr_data: TestRequestData,
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    condition_of_sample: str,
    include_protocol: bool = True,
) -> None:
    print(f"\n[{label}]")
    client_dir = out_dir / label
    ctr_dir = client_dir / "ctr"
    protocol_dir = client_dir / "protocol"
    report_dir = client_dir / "final_report"

    ctr_pdf = generate_pdf_bytes(
        ctr_data, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(ctr_dir / suggest_pdf_filename(ctr_data), ctr_pdf)

    ctr_docx = fill_docx_bytes(
        ctr_data, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(ctr_dir / suggest_docx_filename(ctr_data), ctr_docx)

    if include_protocol:
        docx_bytes, pdf_bytes, docx_name, pdf_name, _ = generate_protocol_documents(
            sample,
            header,
            results,
            generated_by=GENERATED_BY,
            generated_at=GENERATED_AT,
        )
        _write(protocol_dir / _safe_filename(docx_name), docx_bytes)
        if pdf_bytes:
            _write(protocol_dir / _safe_filename(pdf_name), pdf_bytes)

    report = generate_final_report(
        sample,
        header,
        results,
        report_date=header.date_of_analysis,
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        condition_of_sample=condition_of_sample,
    )
    if report.docx_bytes:
        _write(report_dir / _safe_filename(report.docx_filename), report.docx_bytes)
    if report.pdf_bytes:
        _write(report_dir / _safe_filename(report.pdf_filename), report.pdf_bytes)


def generate_water(out: Path) -> None:
    lab = "SLS/26/638"
    customer = Customer(
        customer_name="ABC Foods Pvt Ltd",
        address="Plot 12, MIDC, Nashik, Maharashtra",
        contact_person="Mr. Ramesh Patil",
        contact_number="9876543210",
        email="ramesh@abcfoods.in",
        gst_number="27AAAAA0000A1Z5",
    )
    sample_row = SampleRow(
        sr_no=1,
        sample_name="Potable Water",
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
        category="water",
        test_keys=WATER_TEST_KEYS,
        **_verification(lab),
    )
    ctr = _ctr_request(
        customer=customer,
        lab_code=lab,
        sample=sample_row,
        request_date=date(2026, 7, 27),
    )
    sample = _sample_record(
        sample_id=1,
        request_id=1,
        lab_code=lab,
        category="water",
        sample_name="Potable Water",
        tests_json=WATER_TEST_KEYS,
        customer_name=customer.customer_name,
        customer_address=customer.address,
        batch_code="---",
        quantity="1 lit",
        parameters="Drinking Water",
    )
    header = _header(
        1,
        protocol_no="P-W-2026-001",
        appearance_text="Colorless transparent liquid",
    )
    generate_client_bundle(
        out,
        label="01_water_abc_foods",
        ctr_data=ctr,
        sample=sample,
        header=header,
        results=_water_results(),
        condition_of_sample="Packed in plastic container",
    )


def generate_micro(out: Path) -> None:
    lab = "SLS/26/546"
    customer = Customer(
        customer_name="XYZ Caterers",
        address="Baner Road, Pune, Maharashtra",
        contact_person="Ms. Priya Deshmukh",
        contact_number="9123456780",
        email="priya@xyzcaterers.com",
        gst_number="27BBBBB0000B1Z6",
    )
    sample_row = SampleRow(
        sr_no=1,
        sample_name="Cooked Food: Paneer Gravy",
        quantity="250 gm",
        parameters="Paneer Gravy",
        category="micro",
        test_keys=MICRO_TEST_KEYS,
        **_verification(lab),
    )
    ctr = _ctr_request(
        customer=customer,
        lab_code=lab,
        sample=sample_row,
        request_date=date(2026, 7, 4),
    )
    sample = _sample_record(
        sample_id=2,
        request_id=2,
        lab_code=lab,
        category="micro",
        sample_name="Cooked Food: Paneer Gravy",
        tests_json=MICRO_TEST_KEYS,
        customer_name=customer.customer_name,
        customer_address=customer.address,
        quantity="250 gm",
        parameters="Paneer Gravy",
        sampling_by_lab=False,
    )
    header = _header(
        2,
        protocol_no="P-M-2026-001",
        sample_received_on=date(2026, 7, 4),
        date_of_analysis=date(2026, 7, 9),
        appearance_text="Reddish orange coloured Paneer gravy.",
    )
    results = _micro_results()

    print("\n[02_micro_xyz_caterers]")
    client_dir = out / "02_micro_xyz_caterers"
    ctr_dir = client_dir / "ctr"
    protocol_dir = client_dir / "protocol"
    report_dir = client_dir / "final_report"

    ctr_pdf = generate_pdf_bytes(
        ctr, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(ctr_dir / suggest_pdf_filename(ctr), ctr_pdf)
    ctr_docx = fill_docx_bytes(
        ctr, generated_by=GENERATED_BY, generated_at=GENERATED_AT
    )
    _write(ctr_dir / suggest_docx_filename(ctr), ctr_docx)

    micro_proto = fill_micro_protocol_docx_bytes(
        sample,
        header,
        results,
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
    )
    _write(protocol_dir / suggest_micro_protocol_filename(sample), micro_proto)

    report = generate_final_report(
        sample,
        header,
        results,
        report_date=header.date_of_analysis,
        generated_by=GENERATED_BY,
        generated_at=GENERATED_AT,
        condition_of_sample="Company packing",
    )
    if report.docx_bytes:
        _write(report_dir / _safe_filename(report.docx_filename), report.docx_bytes)
    if report.pdf_bytes:
        _write(report_dir / _safe_filename(report.pdf_filename), report.pdf_bytes)


def generate_food(out: Path) -> None:
    lab = "SLS/26/701"
    nutrition_keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    customer = Customer(
        customer_name="NutriHealth Foods",
        address="Andheri East, Mumbai, Maharashtra",
        contact_person="Mr. Anil Shah",
        contact_number="9988776655",
        email="anil@nutrihealth.in",
        gst_number="27CCCCC0000C1Z7",
    )
    sample_row = SampleRow(
        sr_no=1,
        sample_name="Protein Supplement Mix",
        batch_code="BN-2026-07",
        quantity="500 g",
        parameters="Basic Nutrition",
        package_type="basic_nutrition",
        category="food",
        test_keys=nutrition_keys,
        **_verification(lab),
    )
    ctr = _ctr_request(
        customer=customer,
        lab_code=lab,
        sample=sample_row,
        request_date=date(2026, 7, 30),
    )
    sample = _sample_record(
        sample_id=3,
        request_id=3,
        lab_code=lab,
        category="food",
        sample_name="Protein Supplement Mix",
        tests_json=nutrition_keys,
        customer_name=customer.customer_name,
        customer_address=customer.address,
        batch_code="BN-2026-07",
        quantity="500 g",
        package_type="basic_nutrition",
    )
    header = _header(
        3,
        protocol_no="P-F-2026-001",
        appearance_text="Brown granular powder",
    )
    generate_client_bundle(
        out,
        label="03_food_nutrihealth",
        ctr_data=ctr,
        sample=sample,
        header=header,
        results=_nutrition_results(),
        condition_of_sample="Sealed poly pouch",
    )


def _jaggery_results() -> list[TestResultRow]:
    """Demo Jaggery results with worksheet inputs so protocol PDFs show printed readings."""
    moisture_pct = 3.53
    w_sample = 5.0
    w1_moisture = 55.0
    w2_moisture = w1_moisture - moisture_pct * w_sample / 100.0

    def _ash_inputs(dry_pct: float) -> dict:
        wet = dry_pct * (100.0 - moisture_pct) / 100.0
        w1 = 45.0958
        w2 = w1 + wet * w_sample / 100.0
        return {
            "w1": w1,
            "before_ign": w1 + w_sample,
            "w": w_sample,
            "after_ign": w2,
            "w2": w2,
            "moisture_pct": moisture_pct,
        }

    extraneous_wet = 0.15 * (100.0 - moisture_pct) / 100.0
    w_filter = 1.0120
    w_matter = w_filter + extraneous_wet * w_sample / 100.0

    invert_wet = 93.08 * (100.0 - moisture_pct) / 100.0
    invert_wt = 5.0180
    invert_br = 10.0
    invert_conc = invert_wet * invert_wt * invert_br / (250.0 * 100.0)

    reducing_wet = 11.69 * (100.0 - moisture_pct) / 100.0
    reducing_wt = 5.0180
    reducing_br = 10.0
    reducing_conc = reducing_wet * reducing_wt * reducing_br / (250.0 * 10.0)

    so2_wt = 25.0180
    so2_ug = 8.35 * so2_wt / 10.0

    values_inputs: dict[str, tuple[str, dict | None, float | None]] = {
        "moisture": (
            "3.53",
            {
                "empty_dish": 50.0,
                "w1": w1_moisture,
                "w": w_sample,
                "after_dry": w2_moisture,
                "w2": w2_moisture,
            },
            3.53,
        ),
        "total_ash": ("1.22", _ash_inputs(1.22), 1.22),
        "acid_insoluble_ash": ("0.17", _ash_inputs(0.17), 0.17),
        "added_color": ("Absent", {"color_result": "Absent"}, None),
        "extraneous_matter": (
            "0.15",
            {
                "w": w_sample,
                "w2_filter": w_filter,
                "w1_matter": w_matter,
                "moisture_pct": moisture_pct,
            },
            0.15,
        ),
        "invert_sugar": (
            "93.08",
            {
                "sample_wt": invert_wt,
                "fehling_invert": 25.0,
                "br_invert": invert_br,
                "sugar_conc": invert_conc,
                "moisture_pct": moisture_pct,
            },
            93.08,
        ),
        "reducing_sugar": (
            "11.69",
            {
                "sample_wt": reducing_wt,
                "fehling_reducing": 25.0,
                "br_reducing": reducing_br,
                "sugar_conc": reducing_conc,
                "moisture_pct": moisture_pct,
            },
            11.69,
        ),
        "sucrose": ("77.32", {}, 77.32),
        "sulphated_ash": ("1.22", _ash_inputs(1.22), 1.22),
        "sulphur_dioxide": (
            "8.35",
            {"sample_wt": so2_wt, "ug_so4": so2_ug},
            8.35,
        ),
    }
    rows = []
    for key in JAGGERY_TEST_KEYS:
        if key == "appearance":
            continue
        if key not in values_inputs:
            continue
        val, inputs, num = values_inputs[key]
        rows.append(
            _result_row(
                key,
                val,
                result_numeric=num,
                inputs=inputs or {},
            )
        )
    return rows


def generate_food_jaggery(out: Path) -> None:
    lab = "SLS/26/562"
    with_logo = ["moisture", "total_ash", "acid_insoluble_ash", "added_color"]
    without_logo = ["invert_sugar", "reducing_sugar", "sucrose", "sulphated_ash"]
    test_keys = with_logo + without_logo + ["sulphur_dioxide"]
    customer = Customer(
        customer_name="DK Brothers",
        address="Plot No.23, Gate No. 3, MIDC, Nashik, Maharashtra",
        contact_person="Mr. DK Patil",
        contact_number="9876501234",
        email="info@dkbrothers.in",
        gst_number="27DDDDD0000D1Z8",
    )
    sample_row = SampleRow(
        sr_no=1,
        sample_name="Jaggery",
        batch_code="07 (July 2026)",
        quantity="900 g",
        parameters="Kesar Desi Gud 5",
        package_type="fssai",
        category="food",
        test_keys=test_keys,
        **_verification(lab),
    )
    ctr = _ctr_request(
        customer=customer,
        lab_code=lab,
        sample=sample_row,
        request_date=date(2026, 7, 7),
    )
    sample = _sample_record(
        sample_id=4,
        request_id=4,
        lab_code=lab,
        category="food",
        sample_name="Jaggery",
        tests_json=test_keys,
        customer_name=customer.customer_name,
        customer_address=customer.address,
        batch_code="07 (July 2026)",
        quantity="900 g",
        parameters="Kesar Desi Gud 5",
        package_type="fssai",
        report_format="both",
        tests_with_logo_json=json.dumps(with_logo),
        tests_without_logo_json=json.dumps(without_logo),
        sampling_by_lab=False,
    )
    header = _header(
        4,
        protocol_no="P-J-2026-001",
        sample_received_on=date(2026, 7, 7),
        date_of_analysis=date(2026, 7, 14),
        appearance_text="Brown colored solid jaggery.",
    )
    generate_client_bundle(
        out,
        label="04_food_dk_jaggery",
        ctr_data=ctr,
        sample=sample,
        header=header,
        results=_jaggery_results(),
        condition_of_sample="Packed in company packing",
    )


def _check_templates() -> None:
    templates = [
        PROJECT_ROOT / "reference" / "Customer Test Request form LLP.docx",
        PROJECT_ROOT / "reference" / "Water protocol 2025.docx",
        PROJECT_ROOT / "reference" / "Micro Protocol.docx",
        PROJECT_ROOT / "reference" / "Basic Nutrition Protocol 2026.docx",
        PROJECT_ROOT / "reference" / "Water test report.docx",
        PROJECT_ROOT / "reference" / "Micro Test Report.docx",
        PROJECT_ROOT / "reference" / "Test Report Format.docx",
    ]
    missing = [t.name for t in templates if not t.exists()]
    if missing:
        print(f"Warning: missing templates: {', '.join(missing)}")


def _run_offline() -> None:
    generate_water(OUTPUT_ROOT)
    generate_micro(OUTPUT_ROOT)
    generate_food(OUTPUT_ROOT)
    generate_food_jaggery(OUTPUT_ROOT)


def _run_app_flow() -> None:
    from services.e2e_app_flow import run_all_demo_scenarios

    codes = run_all_demo_scenarios(OUTPUT_ROOT, PROJECT_ROOT)
    print("\nDB-backed sample codes:")
    for code in codes:
        print(f"  - {code}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate E2E demo document bundles.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use legacy in-memory demo data (no database).",
    )
    args = parser.parse_args()

    print(f"E2E output: {OUTPUT_ROOT}")
    _check_templates()

    if args.offline:
        print("Mode: offline (in-memory demo data)")
        _run_offline()
    else:
        print("Mode: app flow (Reception -> Analyst -> Reviewer via PostgreSQL)")
        _run_app_flow()

    print(f"\nDone. Open: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
