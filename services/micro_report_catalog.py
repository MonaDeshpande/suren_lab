"""
services/micro_report_catalog.py
--------------------------------
Fixed microbiological panel: names, limits, and methods for Micro final reports.

Reference: reference/Micro Test Report.htm
Metadata is read from catalog_test_specs (DB).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.catalog_specs import get_spec
from services.protocols.test_catalog import MICRO_TEST_KEYS, get_test

MICRO_REPORT_SECTION_TITLE = "Microbiological Test"

MICRO_REPORT_QSF = "QSF No -7.8.2"

MICRO_DISCLAIMER_LINES: list[str] = [
    "1. Sample submitted by the customer in their own container.",
    "2. Above analysis result is valid only for specific sample and parameters tested.",
    "3. We claim no responsibility for the changes in the characteristic of samples "
    "after dispatch of the Report.",
    "4. Sample stored for one Week and test Report for one year from the date received.",
    "5. Duplicate copies of Report or Invoice will be charged extra.",
]

MICRO_END_OF_REPORT = "****** End of Report ******"


@dataclass(frozen=True)
class MicroReportSpec:
    """Fixed Name / Limits / Method for one micro catalog test."""

    key: str
    sr_no: str
    name: str
    limits: str
    method: str


# Built-in defaults — seeded into catalog_test_specs; runtime reads DB via spec_for_key().
MICRO_REPORT_SPECS: dict[str, MicroReportSpec] = {
    "total_plate_count": MicroReportSpec(
        key="total_plate_count",
        sr_no="1",
        name="Total Plate Count",
        limits="<5.0 x 10⁴ cfu/g",
        method="IS:5402:2018",
    ),
    "t_coliform": MicroReportSpec(
        key="t_coliform",
        sr_no="2",
        name="T.coliform",
        limits="Shall be Absent",
        method="IS 5401(Part-2):2018",
    ),
    "e_coli": MicroReportSpec(
        key="e_coli",
        sr_no="3",
        name="E. Coli",
        limits="Shall be Absent",
        method="IS 5887 (Part - 1 ) : 1976 RA 2018",
    ),
    "salmonella": MicroReportSpec(
        key="salmonella",
        sr_no="4",
        name="Salmonella",
        limits="Shall be Absent",
        method="IS 5887 (Part - 3) : 1999 : RA 2018",
    ),
    "staphylococcus_aureus": MicroReportSpec(
        key="staphylococcus_aureus",
        sr_no="5",
        name="Staphylococcus aureus",
        limits="Shall be Absent",
        method="IS 5887 ( Part - 8/Sec-1) :RA 2018",
    ),
    "yeast_and_mould": MicroReportSpec(
        key="yeast_and_mould",
        sr_no="6",
        name="Yeast and Mould",
        limits="Shall be Absent",
        method="IS 5403:1999 RA 2018",
    ),
}


def micro_report_keys_ordered(selected: Optional[set[str]] = None) -> list[str]:
    """Catalog keys for micro customer report in reference order."""
    if selected is None:
        return list(MICRO_TEST_KEYS)
    return [k for k in MICRO_TEST_KEYS if k in selected]


def spec_for_key(key: str) -> MicroReportSpec:
    """Return report spec from DB catalog; falls back to built-in defaults."""
    spec = get_spec(key)
    if spec is not None:
        try:
            sr = str(MICRO_TEST_KEYS.index(key) + 1)
        except ValueError:
            sr = ""
        return MicroReportSpec(
            key=key,
            sr_no=sr,
            name=spec.test_name,
            limits=spec.limits_display,
            method=spec.method_of_analysis,
        )
    if key in MICRO_REPORT_SPECS:
        return MICRO_REPORT_SPECS[key]
    try:
        test = get_test(key)
    except KeyError:
        test = None
    return MicroReportSpec(
        key=key,
        sr_no="",
        name=test.name if test else key,
        limits="",
        method=test.method if test else "",
    )
