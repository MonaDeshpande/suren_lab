"""
services/water_report_catalog.py
--------------------------------
IS 10500:2018 limits, report labels, and section grouping for water test reports.

Reference: reference/Water test report.docx
Protocol-only tests (e.g. calcium_caco3) are excluded from customer reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Keys used on the customer report (calcium_caco3 is protocol worksheet only).
WATER_REPORT_CHEMICAL_KEYS: list[str] = [
    "ph",
    "tds",
    "chlorides",
    "total_alkalinity",
    "conductivity",
    "total_hardness",
]

WATER_REPORT_ELEMENTAL_KEYS: list[str] = [
    "calcium_ca",
    "magnesium",
]

WATER_REPORT_PHYSICAL_KEYS: list[str] = [
    "odor",
    "turbidity",
]

WATER_REPORT_EXCLUDED_KEYS: frozenset[str] = frozenset({"calcium_caco3"})

WATER_REPORT_ALL_CATALOG_KEYS: list[str] = (
    WATER_REPORT_CHEMICAL_KEYS
    + WATER_REPORT_ELEMENTAL_KEYS
    + WATER_REPORT_PHYSICAL_KEYS
)

# Table 1 row index → catalog key (reference Water test report.docx)
WATER_REPORT_CHEMICAL_TABLE_ROWS: dict[int, str] = {
    3: "ph",
    4: "tds",
    5: "chlorides",
    6: "total_alkalinity",
    7: "conductivity",
    8: "total_hardness",
}

WATER_REPORT_ELEMENTAL_TABLE_ROWS: dict[int, str] = {
    10: "calcium_ca",
    11: "magnesium",
}

WATER_REPORT_PHYSICAL_TABLE_ROWS: dict[int, str] = {
    3: "odor",
    4: "turbidity",
}

DEFAULT_TESTING_CONDUCTED_AT = (
    "Temperature – 25°C ±2°C, Humidity – 55 % ±10 %"
)

WATER_REPORT_REMARK_CHEMICAL = (
    "Remark: The sample analyzed confirms as per IS 10500:2018 Standards "
    "with respect to above tests performed. The Results are pertaining to "
    "the sample sent for analysis only."
)

WATER_REPORT_REMARK_MICRO = (
    "Remark:   The sample analyzed confirm as per IS 10500:2018 Standards "
    "with respect to the above tests performed. The Results are pertaining "
    "to the sample sent for analysis only"
)


@dataclass(frozen=True)
class WaterReportLimits:
    desirable: str = ""
    permissible: str = ""


@dataclass(frozen=True)
class WaterMicroPlaceholder:
    """Micro rows on report until micro protocol is integrated."""

    key: str
    sr_no: str
    name: str
    desirable: str
    permissible: str
    method: str


WATER_REPORT_LIMITS: dict[str, WaterReportLimits] = {
    "ph": WaterReportLimits(desirable="6.5 - 8.5", permissible=""),
    "tds": WaterReportLimits(desirable="Max.500 mg/l", permissible="Max.2000 mg/l"),
    "chlorides": WaterReportLimits(
        desirable="Max.250 mg/l", permissible="Max.1000 mg/l"
    ),
    "total_alkalinity": WaterReportLimits(
        desirable="Max.200 mg/l", permissible="Max.600 mg/l"
    ),
    "conductivity": WaterReportLimits(desirable="--", permissible=""),
    "total_hardness": WaterReportLimits(
        desirable="Max.200 mg/l", permissible="Max.600 mg/l"
    ),
    "calcium_ca": WaterReportLimits(
        desirable="Max.75 mg/l", permissible="Max.200 mg/l"
    ),
    "magnesium": WaterReportLimits(
        desirable="Max.30.0 mg/l", permissible="Max.100 mg/l"
    ),
    "odor": WaterReportLimits(desirable="Agreeable", permissible=""),
    "turbidity": WaterReportLimits(
        desirable="Max.1 NTU", permissible="Max.5 NTU"
    ),
}

WATER_REPORT_METHOD_LABELS: dict[str, str] = {
    "ph": "IS 3025 (P-11)",
    "tds": "IS 3025 (P-16)",
    "chlorides": "IS 3025 (P-32)",
    "total_alkalinity": "IS 3025 (P-23)",
    "conductivity": "IS 3025 (P-14)",
    "total_hardness": "IS 3025 (P-21)",
    "calcium_ca": "IS 3025 (P-40)",
    "magnesium": "IS 3025 (P-46)",
    "odor": "IS 3025 (P-5)",
    "turbidity": "IS 3025 (P-10)",
}

WATER_REPORT_TEST_NAMES: dict[str, str] = {
    "ph": "pH at 25°C",
    "tds": "Total Dissolved Solids\n(TDS)",
    "chlorides": "Chlorides as Cl",
    "total_alkalinity": "Total Alkalinity as CaCO3",
    "conductivity": "Conductivity at 25°C",
    "total_hardness": "Total Hardness as CaCO3",
    "calcium_ca": "Calcium as Ca",
    "magnesium": "Magnesium as Mg",
    "odor": "Odor",
    "turbidity": "Turbidity",
}

# Map final-report placeholder keys to water protocol observation keys.
WATER_MICRO_PROTOCOL_KEY_MAP: dict[str, str] = {
    "t_coliform": "water_total_coliform",
    "e_coli": "water_e_coli",
}

WATER_MICRO_PLACEHOLDERS: list[WaterMicroPlaceholder] = [
    WaterMicroPlaceholder(
        key="t_coliform",
        sr_no="4",
        name="T. Coli form Bacteria",
        desirable="Absent/100ml",
        permissible="",
        method="IS 1622",
    ),
    WaterMicroPlaceholder(
        key="e_coli",
        sr_no="5",
        name="Eschericia coli",
        desirable="Absent/100ml",
        permissible="",
        method="IS 1622",
    ),
]


def water_report_keys_ordered(selected: set[str]) -> list[str]:
    """Catalog keys for water customer report in reference section order."""
    ordered: list[str] = []
    for key in WATER_REPORT_ALL_CATALOG_KEYS:
        if key in selected and key not in WATER_REPORT_EXCLUDED_KEYS:
            ordered.append(key)
    return ordered


def limits_for_key(
    key: str,
    overrides: Optional[dict[str, WaterReportLimits]] = None,
) -> WaterReportLimits:
    if overrides and key in overrides:
        return overrides[key]
    from services.catalog_specs import get_spec

    spec = get_spec(key)
    if spec is not None:
        return WaterReportLimits(
            desirable=spec.limits_desirable or "",
            permissible=spec.limits_permissible or "",
        )
    return WATER_REPORT_LIMITS.get(key, WaterReportLimits())


def method_for_key(key: str) -> str:
    from services.catalog_specs import get_spec

    spec = get_spec(key)
    if spec is not None and spec.method_of_analysis:
        return spec.method_of_analysis
    return WATER_REPORT_METHOD_LABELS.get(key, "")


def report_name_for_key(key: str) -> str:
    from services.catalog_specs import get_spec

    spec = get_spec(key)
    if spec is not None and spec.test_name:
        return spec.test_name
    return WATER_REPORT_TEST_NAMES.get(key, key)
