"""
services/ctr_verification.py
----------------------------
Shared CTR sample-page and verification-checklist helpers for PDF/DOCX output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from services.protocols.test_catalog import (
    CATEGORY_MICRO,
    CATEGORY_WATER,
    TEST_CATALOG,
    default_test_keys_for_category,
    filter_keys_for_category,
    normalize_category,
)
from services.ctr_symbols import normalize_ctr_display_text, yes_no_remark
from services.requests import SampleRow


@dataclass(frozen=True)
class ChecklistRow:
    sr: int
    particular: str
    remark: str


def verification_yes_no_remark(value: Optional[bool]) -> str:
    """Match checklist Yes ( ✓ ) No (  ) layout."""
    return yes_no_remark(value)


def _fmt_verify_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def ctr_test_names_for_sample(sample: SampleRow) -> list[str]:
    """Catalog test display names for the tests block below each sample table."""
    cat = normalize_category(sample.category)
    keys = list(sample.test_keys or [])
    if not keys and cat in (CATEGORY_WATER, CATEGORY_MICRO):
        keys = default_test_keys_for_category(cat)
    keys = filter_keys_for_category(keys, cat)
    names = [
        normalize_ctr_display_text(TEST_CATALOG[k].name)
        for k in keys
        if k in TEST_CATALOG
    ]
    if names:
        return names
    param = (sample.parameters or "").strip()
    if param:
        return [part.strip() for part in param.split(",") if part.strip()]
    return []


def verification_checklist_rows(
    sample: SampleRow,
    *,
    storage_temperature: str = "",
) -> list[ChecklistRow]:
    """Sample Verification Checklist rows (table 1 only)."""
    temp = (storage_temperature or sample.storage_temperature or "").strip()
    return [
        ChecklistRow(1, "Review Date", _fmt_verify_date(sample.verify_review_date)),
        ChecklistRow(2, "Lab Code", (sample.verify_lab_code or "").strip()),
        ChecklistRow(
            3,
            "Sample Code",
            (sample.verify_sample_code or sample.sample_code or "").strip(),
        ),
        ChecklistRow(4, "Storage Temperature", temp),
        ChecklistRow(
            5, "Sample condition", (sample.verify_sample_condition or "").strip()
        ),
        ChecklistRow(
            6,
            "Checked for Sample Quantity",
            verification_yes_no_remark(sample.verify_qty_checked),
        ),
        ChecklistRow(
            7,
            "Checked for Availability of Chemical",
            verification_yes_no_remark(sample.verify_chemical_available),
        ),
        ChecklistRow(
            8,
            "Checked for Availability of Methods",
            verification_yes_no_remark(sample.verify_methods_available),
        ),
        ChecklistRow(
            9,
            "Informed testing Methods to Customer",
            verification_yes_no_remark(sample.verify_methods_informed),
        ),
        ChecklistRow(
            10,
            "Informed turnaround time to Customer",
            verification_yes_no_remark(sample.verify_tat_informed),
        ),
        ChecklistRow(
            11,
            "Sample is ready to issue",
            verification_yes_no_remark(sample.verify_ready_to_issue),
        ),
        ChecklistRow(
            12,
            "About statement of conformity:",
            verification_yes_no_remark(sample.verify_conformity_statement),
        ),
    ]


CHECKLIST_TITLE = "Sample Verification Checklist"
SAMPLE_SECTION_HEADING = "Sample Description & tests to be performed:"
SAMPLE_TABLE_HEADERS = (
    "Sr. No",
    "Name of sample",
    "Code/batch no.",
    "Sample qty.",
    "Parameters",
)

CUSTOMER_SIGNATURE_LABEL = "Customer Signature & date:"


def ctr_signature_date(
    generated_at: str = "",
    request_date: date | None = None,
) -> str:
    """Date shown on page-1 Receiver block (save time, else request date, else today)."""
    stamp = (generated_at or "").strip()
    if stamp and " " in stamp:
        iso = stamp.split()[0]
        try:
            parsed = date.fromisoformat(iso)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            return iso
    if stamp:
        return stamp
    if request_date is not None:
        return request_date.strftime("%d/%m/%Y")
    return date.today().strftime("%d/%m/%Y")
