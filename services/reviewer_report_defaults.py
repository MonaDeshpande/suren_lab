"""
services/reviewer_report_defaults.py
------------------------------------
Default final-report header fields for the Reviewer UI (food reports).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from services.audit import now_lab
from services.protocol_store import ProtocolHeader
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    normalize_category,
)
from services.samples import SampleRecord
from services.ulr import generate_ulr_no, lab_code_for_ulr


def default_customer_name_address(sample: SampleRecord) -> str:
    parts = [sample.customer_name or ""]
    if (sample.customer_address or "").strip():
        parts.append(sample.customer_address.strip())
    return "\n".join(p for p in parts if p)


def default_customer_sample_id_for_report(sample: SampleRecord) -> str:
    """CTR / report Customer Sample ID default by category."""
    cat = normalize_category(sample.category)
    if cat in (CATEGORY_FOOD,):
        return (sample.sample_name or "").strip()
    if cat == CATEGORY_WATER:
        return (sample.parameters or "").strip() or "Drinking Water"
    if cat == CATEGORY_MICRO:
        return (sample.parameters or "").strip() or (sample.sample_name or "")
    return (sample.parameters or "").strip() or (sample.sample_name or "")


def default_lab_code_for_report(sample: SampleRecord) -> str:
    return (sample.sample_code or sample.lab_code or "").strip()


def default_reviewer_report_fields(
    sample: SampleRecord,
    header: ProtocolHeader | None = None,
) -> dict[str, Any]:
    """
    Prefill Reviewer widgets for food final reports.

    header is accepted for future protocol-driven defaults; receipt/analysis
    dates stay read-only on the report from protocol today.
    """
    _ = header
    return {
        "ulr": generate_ulr_no(
            lab_code_for_ulr(sample.lab_code, sample.sample_code)
        ),
        "report_date": now_lab().date(),
        "customer_addr": default_customer_name_address(sample),
        "customer_sid": default_customer_sample_id_for_report(sample),
        "batch_no": (sample.batch_code or "").strip(),
        "lab_code": default_lab_code_for_report(sample),
    }
