"""
services/reviewer_report.py
---------------------------
Assemble Reviewer form state into generate_final_report() arguments.

Keeps pages/3_Reviewer.py focused on UI; generation stays in test_report_pdf.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import pandas as pd

from services.protocol_store import ProtocolHeader, TestResultRow
from services.report_settings import ReportSettings, signatory_role
from services.samples import SampleRecord
from services.test_report_micro_docx import MicroReportFillOptions
from services.test_report_pdf import (
    FinalReportOutput,
    default_checked_by_analysts,
    generate_final_report,
)
from services.test_report_water_docx import WaterReportFillOptions
from services.water_report_catalog import WaterReportLimits


@dataclass
class ReviewerGenerationParams:
    """Keyword arguments for generate_final_report from Reviewer form state."""

    generated_by: str
    generated_at: str
    condition_of_sample: str
    tests_processed: str | None
    specification_by_test_name: dict[str, str] | None
    water_opts: WaterReportFillOptions | None
    micro_opts: MicroReportFillOptions | None
    ulr_no: str | None
    location_of_sampling: str | None
    sampling_method: str | None
    authorized_signatory: str | None
    checked_by: str | None
    remark_text: str | None
    disclaimer_bullets: list[str] | None
    report_date: date | None
    customer_name_address: str | None
    customer_sample_id: str | None
    batch_no: str | None
    lab_code: str | None


def _parse_report_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    return None


def _parse_specs_df(
    specs_df: pd.DataFrame | None,
    *,
    is_water: bool,
    is_micro: bool,
) -> tuple[dict[str, WaterReportLimits], dict[str, str]]:
    limit_overrides: dict[str, WaterReportLimits] = {}
    specification_by_test_name: dict[str, str] = {}
    if specs_df is None or specs_df.empty:
        return limit_overrides, specification_by_test_name

    if is_water:
        for _, row in specs_df.iterrows():
            test_key = str(row["Test"])
            limit_overrides[test_key] = WaterReportLimits(
                desirable=str(row.get("Desirable Limit", "") or ""),
                permissible=str(row.get("Permissible limit", "") or ""),
            )
    elif not is_micro:
        for _, row in specs_df.iterrows():
            specification_by_test_name[str(row["Test"])] = str(
                row.get("Specification", "") or ""
            )
    return limit_overrides, specification_by_test_name


def build_generation_params(
    sample: SampleRecord,
    *,
    is_water: bool,
    is_micro: bool,
    specs_df: pd.DataFrame | None,
    sample_code: str,
    report_settings: ReportSettings,
    generated_by: str,
    generated_at: str,
    get_field: Callable[[str, str], Any],
) -> ReviewerGenerationParams:
    """Map Reviewer widget values to generate_final_report keyword arguments."""
    limit_overrides, specification_by_test_name = _parse_specs_df(
        specs_df,
        is_water=is_water,
        is_micro=is_micro,
    )

    auth_name = str(get_field("auth_signatory", sample_code) or "")
    check_name = (
        str(get_field("checked_by", sample_code) or "")
        or default_checked_by_analysts(sample)
    )
    auth_role = signatory_role(auth_name, report_settings)
    check_role = "Analyst" if check_name else "Quality Manager"

    water_opts = None
    micro_opts = None
    if is_water:
        water_opts = WaterReportFillOptions(
            ulr_no=str(get_field("ulr", sample_code) or ""),
            report_no_chemical=str(get_field("report_chem", sample_code) or ""),
            report_no_micro=str(get_field("report_micro", sample_code) or ""),
            condition_of_sample=str(get_field("condition", sample_code) or ""),
            customer_sample_id=str(get_field("customer_sid", sample_code) or ""),
            sample_appearance=str(get_field("appearance", sample_code) or ""),
            testing_conducted_at=str(get_field("testing_at", sample_code) or ""),
            limit_overrides=limit_overrides,
            generated_by=generated_by,
            generated_at=generated_at,
            authorized_signatory=auth_name,
            checked_by=check_name,
            authorized_signatory_role=auth_role,
            checked_by_role=check_role,
        )
    elif is_micro:
        micro_opts = MicroReportFillOptions(
            report_no=str(get_field("report_no", sample_code) or ""),
            condition_of_sample=str(get_field("condition", sample_code) or ""),
            customer_sample_id=str(get_field("customer_sid", sample_code) or ""),
            sample_appearance=str(get_field("appearance", sample_code) or ""),
            generated_by=generated_by,
            generated_at=generated_at,
            authorized_signatory=auth_name,
            checked_by=check_name,
            authorized_signatory_role=auth_role,
            checked_by_role=check_role,
        )

    disclaimer_raw = str(get_field("disclaimer", sample_code) or "")
    disclaimer_bullets = (
        [ln.strip() for ln in disclaimer_raw.splitlines() if ln.strip()]
        if not is_water and not is_micro
        else None
    )

    food_header = None
    if not is_water and not is_micro:
        food_header = {
            "report_date": _parse_report_date(get_field("report_date", sample_code)),
            "customer_name_address": str(
                get_field("customer_addr", sample_code) or ""
            ),
            "customer_sample_id": str(get_field("customer_sid", sample_code) or ""),
            "batch_no": str(get_field("batch_no", sample_code) or ""),
            "lab_code": str(get_field("lab_code", sample_code) or ""),
        }

    return ReviewerGenerationParams(
        generated_by=generated_by,
        generated_at=generated_at,
        condition_of_sample=str(get_field("condition", sample_code) or ""),
        tests_processed=(
            str(get_field("tests_processed", sample_code) or "")
            if not is_water and not is_micro
            else None
        ),
        specification_by_test_name=(
            specification_by_test_name or None
            if not is_water and not is_micro
            else None
        ),
        water_opts=water_opts,
        micro_opts=micro_opts,
        ulr_no=(
            str(get_field("ulr", sample_code) or "")
            if not is_micro
            else None
        ),
        location_of_sampling=(
            str(get_field("location", sample_code) or "")
            if not is_water and not is_micro
            else None
        ),
        sampling_method=(
            str(get_field("sampling_method", sample_code) or "")
            if not is_water and not is_micro
            else None
        ),
        authorized_signatory=auth_name or None,
        checked_by=check_name or None,
        remark_text=(
            str(get_field("remark", sample_code) or "")
            if not is_water and not is_micro
            else None
        ),
        disclaimer_bullets=disclaimer_bullets,
        report_date=food_header["report_date"] if food_header else None,
        customer_name_address=(
            food_header["customer_name_address"] if food_header else None
        ),
        customer_sample_id=(
            food_header["customer_sample_id"] if food_header else None
        ),
        batch_no=food_header["batch_no"] if food_header else None,
        lab_code=food_header["lab_code"] if food_header else None,
    )


def generate_reviewer_final_report(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    params: ReviewerGenerationParams,
) -> FinalReportOutput:
    """Generate the final report using assembled Reviewer parameters."""
    return generate_final_report(
        sample,
        header,
        results,
        report_date=params.report_date,
        generated_by=params.generated_by,
        generated_at=params.generated_at,
        condition_of_sample=params.condition_of_sample,
        tests_processed=params.tests_processed,
        specification_by_test_name=params.specification_by_test_name,
        water_opts=params.water_opts,
        micro_opts=params.micro_opts,
        ulr_no=params.ulr_no,
        location_of_sampling=params.location_of_sampling,
        sampling_method=params.sampling_method,
        authorized_signatory=params.authorized_signatory,
        checked_by=params.checked_by,
        remark_text=params.remark_text,
        disclaimer_bullets=params.disclaimer_bullets,
        customer_name_address=params.customer_name_address,
        customer_sample_id=params.customer_sample_id,
        batch_no=params.batch_no,
        lab_code=params.lab_code,
    )
