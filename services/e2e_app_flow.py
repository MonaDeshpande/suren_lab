"""
services/e2e_app_flow.py
------------------------
Service-layer E2E: Reception -> Analyst -> Reviewer using the live PostgreSQL DB.

Same code paths as the Streamlit pages, without browser automation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from db.connection import get_db, test_connection
from db.migrate import ensure_schema
from services.customers import Customer
from services.ctr_pdf import generate_ctr_documents
from services.docx_filler import suggest_docx_filename
from services.micro_protocol_docx import (
    fill_micro_protocol_docx_bytes,
    suggest_micro_protocol_filename,
)
from services.pdf_generator import suggest_pdf_filename
from services.protocol_pdf import generate_protocol_documents
from services.protocol_store import (
    ProtocolHeader,
    get_protocol_header,
    list_results,
    save_test_result,
    upsert_protocol_header,
)
from services.protocols.test_catalog import (
    JAGGERY_TEST_KEYS,
    MICRO_TEST_KEYS,
    NUTRITION_TEST_KEYS,
    WATER_MICRO_TEST_KEYS,
    WATER_TEST_KEYS,
    default_water_micro_procedure,
)
from services.requests import SampleRow, TestRequestData, get_test_request, save_test_request, validate_request
from services.samples import get_by_code, update_status
from services.test_report_pdf import FinalReportOutput, generate_final_report
from services.test_report_water_docx import WaterReportFillOptions
from services.test_report_micro_docx import MicroReportFillOptions
from services.ulr import generate_ulr_no, lab_code_for_ulr
from services.users import create_user, list_active_analysts

GENERATED_BY = "S_LAB E2E"
GENERATED_AT = "24/08/2026 15:00"
_E2E_ANALYST_PW = "E2E@Temp12"


@dataclass
class E2EScenario:
    """One demo client run through Reception -> Analyst -> Reviewer."""

    label: str
    customer: Customer
    request_date: date
    lab_code: str
    sample: SampleRow
    appearance_text: str
    date_of_analysis: date
    sample_received_on: date
    condition_of_sample: str
    analyst_inputs_by_key: dict[str, dict[str, Any]]
    analyst_input_order: list[str] = field(default_factory=list)
    include_protocol: bool = True
    micro_protocol_only: bool = False
    reviewer_extra: dict[str, Any] = field(default_factory=dict)


def prepare_app_e2e() -> None:
    """Migrate schema and verify PostgreSQL is reachable."""
    ensure_schema()
    ok, msg = test_connection()
    if not ok:
        raise RuntimeError(f"Database not available: {msg}")


def ensure_e2e_analysts() -> tuple[int, int]:
    """
    Return two distinct active analyst user IDs.

    Reuses existing analysts when possible; otherwise creates temporary E2E users.
    """
    analysts = list_active_analysts()
    if len(analysts) >= 2:
        return analysts[0].id, analysts[1].id

    created_ids: list[int] = []
    need = 2 - len(analysts)
    base_ids = [a.id for a in analysts]
    for i in range(need):
        user = create_user(
            username=f"e2e_analyst_{uuid.uuid4().hex[:8]}",
            temporary_password=_E2E_ANALYST_PW,
            roles=["analyst"],
            full_name=f"E2E Analyst {i + 1}",
        )
        created_ids.append(user.id)
    all_ids = base_ids + created_ids
    return all_ids[0], all_ids[1]


def cleanup_e2e_customers(gst_numbers: list[str]) -> None:
    """Remove prior E2E requests/samples for the given customer GST numbers."""
    normalized = [g.strip().upper() for g in gst_numbers if (g or "").strip()]
    if not normalized:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            for gst in normalized:
                cur.execute(
                    """
                    DELETE FROM request_samples
                     WHERE request_id IN (
                        SELECT tr.id FROM test_requests tr
                        JOIN customers c ON c.id = tr.customer_id
                        WHERE c.gst_number = %s
                     )
                    """,
                    (gst,),
                )
                cur.execute(
                    """
                    DELETE FROM test_requests
                     WHERE customer_id IN (
                        SELECT id FROM customers WHERE gst_number = %s
                     )
                    """,
                    (gst,),
                )
                cur.execute("DELETE FROM customers WHERE gst_number = %s", (gst,))


def _verification(lab_code: str) -> dict[str, Any]:
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


def run_reception(scenario: E2EScenario) -> str:
    """Save CTR via Reception services; return sample_code."""
    data = _ctr_request(
        customer=scenario.customer,
        lab_code=scenario.lab_code,
        sample=scenario.sample,
        request_date=scenario.request_date,
    )
    errors = validate_request(data)
    if errors:
        raise ValueError("; ".join(errors))
    saved = save_test_request(data, actor=None)
    if not saved.samples:
        raise RuntimeError("Reception save returned no samples")
    code = (saved.samples[0].sample_code or "").strip()
    if not code:
        raise RuntimeError("Reception save did not assign a sample code")
    return code


def run_analyst(
    sample_code: str,
    scenario: E2EScenario,
    *,
    chem_analyst_id: int,
    micro_analyst_id: int,
) -> None:
    """Enter protocol header and test results like the Analyst page."""
    sample = get_by_code(sample_code)
    if sample is None:
        raise ValueError(f"Sample not found: {sample_code}")

    existing = get_protocol_header(sample.id)
    issued_to = (existing.issued_to if existing else "") or sample.assigned_analyst_name or "E2E Analyst"
    upsert_protocol_header(
        ProtocolHeader(
            sample_id=sample.id,
            protocol_no=scenario.sample.protocol_no,
            issued_to=issued_to,
            issued_by=(existing.issued_by if existing else "E2E Reception"),
            sample_received_on=scenario.sample_received_on,
            date_of_analysis=scenario.date_of_analysis,
            appearance_text=scenario.appearance_text,
        ),
        actor=None,
    )

    order = scenario.analyst_input_order or list(scenario.analyst_inputs_by_key.keys())
    for test_key in order:
        if test_key not in scenario.analyst_inputs_by_key:
            continue
        inputs = scenario.analyst_inputs_by_key[test_key]
        save_test_result(sample.id, test_key, inputs, actor=None)

    update_status(sample_code, "completed", "E2E analyst workflow complete", actor=None)


def run_reviewer(
    sample_code: str,
    scenario: E2EScenario,
    *,
    generated_by: str = GENERATED_BY,
    generated_at: str = GENERATED_AT,
) -> FinalReportOutput:
    """Generate final report and mark sample reported."""
    sample = get_by_code(sample_code)
    if sample is None:
        raise ValueError(f"Sample not found: {sample_code}")
    header = get_protocol_header(sample.id)
    if header is None:
        raise ValueError(f"Protocol header missing for {sample_code}")
    results = list_results(sample.id)
    if not results:
        raise ValueError(f"No analyst results saved for {sample_code}")

    extra = dict(scenario.reviewer_extra)
    ulr = generate_ulr_no(lab_code_for_ulr(sample.lab_code, sample.sample_code))

    water_opts = extra.pop("water_opts", None)
    micro_opts = extra.pop("micro_opts", None)
    if water_opts is None and sample.category == "water":
        water_opts = WaterReportFillOptions(
            ulr_no=ulr,
            condition_of_sample=scenario.condition_of_sample,
            customer_sample_id=(sample.parameters or "").strip() or sample.sample_name,
            sample_appearance=scenario.appearance_text,
            generated_by=generated_by,
            generated_at=generated_at,
        )
    elif isinstance(water_opts, dict):
        water_opts = WaterReportFillOptions(**water_opts)

    if micro_opts is None and sample.category == "micro":
        micro_opts = MicroReportFillOptions(
            condition_of_sample=scenario.condition_of_sample,
            customer_sample_id=(sample.parameters or "").strip() or sample.sample_name,
            sample_appearance=scenario.appearance_text,
            generated_by=generated_by,
            generated_at=generated_at,
        )
    elif isinstance(micro_opts, dict):
        micro_opts = MicroReportFillOptions(**micro_opts)

    output = generate_final_report(
        sample,
        header,
        results,
        report_date=scenario.date_of_analysis,
        generated_by=generated_by,
        generated_at=generated_at,
        condition_of_sample=scenario.condition_of_sample,
        water_opts=water_opts,
        micro_opts=micro_opts,
        ulr_no=ulr if sample.category != "micro" else None,
        **extra,
    )
    update_status(
        sample_code,
        "reported",
        "[E2E Reviewer] Final report generated",
        actor=None,
    )
    return output


def _safe_filename(name: str) -> str:
    return name.replace("/", "-").replace("\\", "-")


def _write(path: Path, data: bytes, *, project_root: Path) -> None:
    path = path.parent / _safe_filename(path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        display = str(path.relative_to(project_root))
    except ValueError:
        display = str(path)
    print(f"  wrote {display} ({len(data):,} bytes)")


def export_bundle(
    *,
    label: str,
    sample_code: str,
    report_output: FinalReportOutput,
    out_dir: Path,
    project_root: Path,
    scenario: E2EScenario,
    generated_by: str = GENERATED_BY,
    generated_at: str = GENERATED_AT,
) -> None:
    """Write CTR, protocol, and final report files from DB-backed data."""
    print(f"\n[{label}] sample_code={sample_code}")
    sample = get_by_code(sample_code)
    if sample is None:
        raise ValueError(f"Sample not found: {sample_code}")
    header = get_protocol_header(sample.id)
    if header is None:
        raise ValueError(f"Protocol header missing for {sample_code}")
    results = list_results(sample.id)

    ctr_data = get_test_request(sample.request_id)
    if ctr_data is None:
        raise ValueError(f"Request not found for sample {sample_code}")

    client_dir = out_dir / label
    ctr_dir = client_dir / "ctr"
    protocol_dir = client_dir / "protocol"
    report_dir = client_dir / "final_report"

    (
        ctr_docx,
        ctr_pdf,
        _ctr_docx_name,
        _ctr_pdf_name,
        ctr_pdf_err,
    ) = generate_ctr_documents(
        ctr_data,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    if ctr_pdf is None:
        raise RuntimeError(f"CTR PDF generation failed: {ctr_pdf_err or 'unknown'}")
    _write(ctr_dir / suggest_pdf_filename(ctr_data), ctr_pdf, project_root=project_root)
    _write(ctr_dir / suggest_docx_filename(ctr_data), ctr_docx, project_root=project_root)

    if scenario.include_protocol:
        if scenario.micro_protocol_only:
            proto = fill_micro_protocol_docx_bytes(
                sample,
                header,
                results,
                generated_by=generated_by,
                generated_at=generated_at,
            )
            _write(
                protocol_dir / suggest_micro_protocol_filename(sample),
                proto,
                project_root=project_root,
            )
        else:
            docx_bytes, pdf_bytes, docx_name, pdf_name, _ = generate_protocol_documents(
                sample,
                header,
                results,
                generated_by=generated_by,
                generated_at=generated_at,
            )
            _write(protocol_dir / _safe_filename(docx_name), docx_bytes, project_root=project_root)
            if pdf_bytes:
                _write(protocol_dir / _safe_filename(pdf_name), pdf_bytes, project_root=project_root)

    if report_output.docx_bytes:
        _write(
            report_dir / _safe_filename(report_output.docx_filename),
            report_output.docx_bytes,
            project_root=project_root,
        )
    if report_output.pdf_bytes:
        _write(
            report_dir / _safe_filename(report_output.pdf_filename),
            report_output.pdf_bytes,
            project_root=project_root,
        )


def run_scenario(
    scenario: E2EScenario,
    out_dir: Path,
    project_root: Path,
    *,
    chem_analyst_id: int,
    micro_analyst_id: int,
) -> str:
    """Full Reception -> Analyst -> Reviewer -> export for one scenario."""
    cleanup_e2e_customers([scenario.customer.gst_number])
    sample_code = run_reception(scenario)
    run_analyst(
        sample_code,
        scenario,
        chem_analyst_id=chem_analyst_id,
        micro_analyst_id=micro_analyst_id,
    )
    report = run_reviewer(sample_code, scenario)
    export_bundle(
        label=scenario.label,
        sample_code=sample_code,
        report_output=report,
        out_dir=out_dir,
        project_root=project_root,
        scenario=scenario,
    )
    return sample_code


# ---------------------------------------------------------------------------
# Analyst input builders (valid save_test_result form fields)
# ---------------------------------------------------------------------------


def _water_analyst_inputs() -> dict[str, dict[str, Any]]:
    proc_tc = default_water_micro_procedure("water_total_coliform")
    proc_ec = default_water_micro_procedure("water_e_coli")
    return {
        "ph": {"ph_value": "7.320"},
        "tds": {"w": "100", "w1": "10.0", "w2": "10.185"},
        "chlorides": {"v3": "50", "v1": "26.0", "v2": "0", "n": "0.01"},
        "total_alkalinity": {"v": "100", "a": "1.9", "n": "0.02"},
        "conductivity": {"conductivity": "285"},
        "total_hardness": {"volume": "50", "a": "6.0", "b": "1.0"},
        "calcium_ca": {"volume": "50", "a": "1.425", "b": "1.0"},
        "calcium_caco3": {"volume": "50", "a": "1.425", "c": "2.0"},
        "magnesium": {},
        "odor": {"odor_obs": "Agreeable"},
        "turbidity": {"turbidity": "0.8"},
        "water_total_coliform": {"procedure": proc_tc, "result_obs": "absent"},
        "water_e_coli": {"procedure": proc_ec, "result_obs": "absent"},
    }


def _water_input_order() -> list[str]:
    return list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS)


def _micro_analyst_inputs() -> dict[str, dict[str, Any]]:
    values = {
        "total_plate_count": {"result_value": "3.0 x 10³ cfu/gm"},
        "t_coliform": {"result_value": "Absent"},
        "e_coli": {"result_value": "Absent"},
        "salmonella": {"result_value": "Absent"},
        "staphylococcus_aureus": {"result_value": "Absent"},
        "yeast_and_mould": {"result_value": "< 10 cfu/gm"},
    }
    return values


def _nutrition_analyst_inputs() -> dict[str, dict[str, Any]]:
    keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    inputs: dict[str, dict[str, Any]] = {
        "appearance": {"appearance_obs": "Brown granular powder"},
        "bn_moisture": {"w1": "10.5", "w2": "10.08", "w": "5.0"},
        "bn_total_ash": {"w1": "20.0", "w2": "20.09", "w": "5.0"},
        "bn_total_fat": {"w": "10.0", "w1": "20.0", "w2": "20.25"},
        "bn_protein": {
            "titrant": "NaOH",
            "w": "5.0",
            "n_naoh": "1.0",
            "br_blank": "10.0",
            "br_sample": "3.04",
            "n_factor": "6.25",
        },
        "bn_crude_fibre": {"w": "5.0", "w1": "20.0", "w2": "20.105"},
        "bn_added_sugar": {"sample_wt": "5.0", "br": "10.0", "sugar_conc": "0.0"},
        "bn_total_sugar": {"sample_wt": "5.0", "br": "10.0", "sugar_conc": "3.25"},
    }
    inputs["bn_carbohydrate"] = {}
    inputs["bn_calories"] = {}
    return {k: inputs[k] for k in keys if k in inputs}


def _nutrition_input_order() -> list[str]:
    keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    ordered = [
        "appearance",
        "bn_moisture",
        "bn_total_ash",
        "bn_total_fat",
        "bn_protein",
        "bn_crude_fibre",
        "bn_added_sugar",
        "bn_total_sugar",
        "bn_carbohydrate",
        "bn_calories",
    ]
    return [k for k in ordered if k in keys]


def _jaggery_analyst_inputs() -> dict[str, dict[str, Any]]:
    moisture_pct = 3.53
    w_sample = 5.0
    w1_moisture = 55.0
    w2_moisture = w1_moisture - moisture_pct * w_sample / 100.0

    def _ash(dry_pct: float) -> dict[str, Any]:
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

    raw: dict[str, dict[str, Any]] = {
        "moisture": {
            "empty_dish": 50.0,
            "w1": w1_moisture,
            "w": w_sample,
            "after_dry": w2_moisture,
            "w2": w2_moisture,
        },
        "total_ash": _ash(1.22),
        "acid_insoluble_ash": _ash(0.17),
        "added_color": {"color_result": "Absent"},
        "extraneous_matter": {
            "w": w_sample,
            "w2_filter": w_filter,
            "w1_matter": w_matter,
            "moisture_pct": moisture_pct,
        },
        "invert_sugar": {
            "sample_wt": invert_wt,
            "fehling_invert": 25.0,
            "br_invert": invert_br,
            "sugar_conc": invert_conc,
            "moisture_pct": moisture_pct,
        },
        "reducing_sugar": {
            "sample_wt": reducing_wt,
            "fehling_reducing": 25.0,
            "br_reducing": reducing_br,
            "sugar_conc": reducing_conc,
            "moisture_pct": moisture_pct,
        },
        "sucrose": {},
        "sulphated_ash": _ash(1.22),
        "sulphur_dioxide": {"sample_wt": so2_wt, "ug_so4": so2_ug},
    }
    return {k: raw[k] for k in JAGGERY_TEST_KEYS if k in raw and k != "appearance"}


def _jaggery_input_order() -> list[str]:
    return [k for k in JAGGERY_TEST_KEYS if k != "appearance"]


def build_demo_scenarios(chem_analyst_id: int, micro_analyst_id: int) -> list[E2EScenario]:
    """Demo scenarios aligned with downloads/e2e_demo folder names."""
    water_lab = "SLS/26/638"
    micro_lab = "SLS/26/546"
    food_lab = "SLS/26/701"
    jaggery_lab = "SLS/26/562"

    nutrition_keys = [k for k in NUTRITION_TEST_KEYS if k != "bn_ash_insoluble_hcl"]
    jaggery_logo = ["moisture", "total_ash", "acid_insoluble_ash", "added_color"]
    jaggery_nologo = ["invert_sugar", "reducing_sugar", "sucrose", "sulphated_ash"]
    jaggery_keys = jaggery_logo + jaggery_nologo + ["sulphur_dioxide"]

    return [
        E2EScenario(
            label="01_water_abc_foods",
            customer=Customer(
                customer_name="ABC Foods Pvt Ltd",
                address="Plot 12, MIDC, Nashik, Maharashtra",
                contact_person="Mr. Ramesh Patil",
                contact_number="9876543210",
                email="ramesh@abcfoods.in",
                gst_number="27E2E000001A1Z5",
            ),
            request_date=date(2026, 7, 27),
            lab_code=water_lab,
            sample=SampleRow(
                sr_no=1,
                sample_name="Potable Water",
                batch_code="---",
                quantity="1 lit",
                parameters="Drinking Water",
                category="water",
                test_keys=list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS),
                assigned_analyst_id=chem_analyst_id,
                assigned_micro_analyst_id=micro_analyst_id,
                protocol_no="P-W-2026-001",
                **_verification(water_lab),
            ),
            appearance_text="Colorless transparent liquid",
            date_of_analysis=date(2026, 7, 30),
            sample_received_on=date(2026, 7, 27),
            condition_of_sample="Packed in plastic container",
            analyst_inputs_by_key=_water_analyst_inputs(),
            analyst_input_order=_water_input_order(),
        ),
        E2EScenario(
            label="02_micro_xyz_caterers",
            customer=Customer(
                customer_name="XYZ Caterers",
                address="Baner Road, Pune, Maharashtra",
                contact_person="Ms. Priya Deshmukh",
                contact_number="9123456780",
                email="priya@xyzcaterers.com",
                gst_number="27E2E000002B1Z6",
            ),
            request_date=date(2026, 7, 4),
            lab_code=micro_lab,
            sample=SampleRow(
                sr_no=1,
                sample_name="Cooked Food: Paneer Gravy",
                quantity="250 gm",
                parameters="Paneer Gravy",
                category="micro",
                test_keys=list(MICRO_TEST_KEYS),
                assigned_analyst_id=chem_analyst_id,
                protocol_no="P-M-2026-001",
                **_verification(micro_lab),
            ),
            appearance_text="Reddish orange coloured Paneer gravy.",
            date_of_analysis=date(2026, 7, 9),
            sample_received_on=date(2026, 7, 4),
            condition_of_sample="Company packing",
            analyst_inputs_by_key=_micro_analyst_inputs(),
            analyst_input_order=list(MICRO_TEST_KEYS),
            micro_protocol_only=True,
        ),
        E2EScenario(
            label="03_food_nutrihealth",
            customer=Customer(
                customer_name="NutriHealth Foods",
                address="Andheri East, Mumbai, Maharashtra",
                contact_person="Mr. Anil Shah",
                contact_number="9988776655",
                email="anil@nutrihealth.in",
                gst_number="27E2E000003C1Z7",
            ),
            request_date=date(2026, 7, 30),
            lab_code=food_lab,
            sample=SampleRow(
                sr_no=1,
                sample_name="Protein Supplement Mix",
                batch_code="BN-2026-07",
                quantity="500 g",
                parameters="Basic Nutrition",
                package_type="basic_nutrition",
                category="food",
                test_keys=nutrition_keys,
                assigned_analyst_id=chem_analyst_id,
                protocol_no="P-F-2026-001",
                **_verification(food_lab),
            ),
            appearance_text="Brown granular powder",
            date_of_analysis=date(2026, 7, 30),
            sample_received_on=date(2026, 7, 27),
            condition_of_sample="Sealed poly pouch",
            analyst_inputs_by_key=_nutrition_analyst_inputs(),
            analyst_input_order=_nutrition_input_order(),
            reviewer_extra={"tests_processed": "Basic Nutrition panel"},
        ),
        E2EScenario(
            label="04_food_dk_jaggery",
            customer=Customer(
                customer_name="DK Brothers",
                address="Plot No.23, Gate No. 3, MIDC, Nashik, Maharashtra",
                contact_person="Mr. DK Patil",
                contact_number="9876501234",
                email="info@dkbrothers.in",
                gst_number="27E2E000004D1Z8",
            ),
            request_date=date(2026, 7, 7),
            lab_code=jaggery_lab,
            sample=SampleRow(
                sr_no=1,
                sample_name="Jaggery",
                batch_code="07 (July 2026)",
                quantity="900 g",
                parameters="Kesar Desi Gud 5",
                package_type="fssai",
                category="food",
                test_keys=jaggery_keys,
                assigned_analyst_id=chem_analyst_id,
                protocol_no="P-J-2026-001",
                report_format="both",
                tests_with_logo=jaggery_logo,
                tests_without_logo=jaggery_nologo,
                **_verification(jaggery_lab),
            ),
            appearance_text="Brown colored solid jaggery.",
            date_of_analysis=date(2026, 7, 14),
            sample_received_on=date(2026, 7, 7),
            condition_of_sample="Packed in company packing",
            analyst_inputs_by_key=_jaggery_analyst_inputs(),
            analyst_input_order=_jaggery_input_order(),
            reviewer_extra={"tests_processed": "Jaggery FSSAI panel"},
        ),
    ]


def run_all_demo_scenarios(out_dir: Path, project_root: Path) -> list[str]:
    """Run all built-in demo scenarios; return sample codes."""
    prepare_app_e2e()
    chem_id, micro_id = ensure_e2e_analysts()
    codes: list[str] = []
    for scenario in build_demo_scenarios(chem_id, micro_id):
        codes.append(
            run_scenario(
                scenario,
                out_dir,
                project_root,
                chem_analyst_id=chem_id,
                micro_analyst_id=micro_id,
            )
        )
    return codes
