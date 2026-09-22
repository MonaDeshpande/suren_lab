"""
services/document_templates.py
------------------------------
Client-editable Word template paths under reference/.

Four header/footer formats (designed in Word at the client site):

  1. CTR          — body: Customer Test Request form LLP.docx;
                    header only: CTR_template.docx (cloned onto filled body)
  2. Protocol     — header/footer reference: protocol.docx (source layout also kept as protocol_1.docx)
  3. Final report — with-logo template per category
  4. Final report — without-logo template per category (separate .docx file)

Replace or edit these files on the client PC; restart Streamlit to pick up changes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.protocols.test_catalog import (
    CATEGORY_MICRO,
    CATEGORY_WATER,
    normalize_category,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = PROJECT_ROOT / "reference"

# --- Format 1: CTR ---
CTR_FORM_BODY_PATH = REFERENCE / "Customer Test Request form LLP.docx"
CTR_LETTERHEAD_PATH = REFERENCE / "CTR_template.docx"
# Backward-compatible alias (body template for form tables)
CTR_TEMPLATE_PATH = CTR_FORM_BODY_PATH

# --- Format 2: Protocol (client copies the same header/footer into each file) ---
PROTOCOL_HEADER_FOOTER_PATH = REFERENCE / "protocol.docx"
PROTOCOL_LETTERHEAD_LOGO_PATH = REFERENCE / "surendra_lab_logo.png"
JAGGERY_PROTOCOL_PATH = REFERENCE / "Jaggery Protocol LLP.docx"
NUTRITION_PROTOCOL_PATH = REFERENCE / "Basic Nutrition Protocol 2026.docx"
WATER_PROTOCOL_PATH = REFERENCE / "Water protocol 2025.docx"
MICRO_PROTOCOL_PATH = REFERENCE / "Micro Protocol.docx"

# --- Formats 3 & 4: Final test reports (with logo / without logo) ---
FOOD_REPORT_WITH_LOGO_PATH = REFERENCE / "Test Report Format.docx"
FOOD_REPORT_WITHOUT_LOGO_PATH = REFERENCE / "Test Report Format (no logo).docx"

WATER_REPORT_WITH_LOGO_PATH = REFERENCE / "Water test report.docx"
WATER_REPORT_WITHOUT_LOGO_PATH = REFERENCE / "Water test report (no logo).docx"

MICRO_REPORT_WITH_LOGO_PATH = REFERENCE / "Micro Test Report.docx"
MICRO_REPORT_WITHOUT_LOGO_PATH = REFERENCE / "Micro Test Report (no logo).docx"

# Backward-compatible aliases (with-logo paths)
FOOD_REPORT_TEMPLATE_PATH = FOOD_REPORT_WITH_LOGO_PATH
WATER_REPORT_TEMPLATE_PATH = WATER_REPORT_WITH_LOGO_PATH
MICRO_REPORT_TEMPLATE_PATH = MICRO_REPORT_WITH_LOGO_PATH


def final_report_template_path(category: str, *, with_logo: bool) -> Path:
    """
    Return the Word template for a final test report section.

    When *with_logo* is False and the without-logo file is missing, falls back
    to the with-logo template and logs a warning (client should add the file).
    """
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        with_path = WATER_REPORT_WITH_LOGO_PATH
        without_path = WATER_REPORT_WITHOUT_LOGO_PATH
    elif cat == CATEGORY_MICRO:
        with_path = MICRO_REPORT_WITH_LOGO_PATH
        without_path = MICRO_REPORT_WITHOUT_LOGO_PATH
    else:
        with_path = FOOD_REPORT_WITH_LOGO_PATH
        without_path = FOOD_REPORT_WITHOUT_LOGO_PATH

    if with_logo:
        return with_path

    if without_path.exists():
        return without_path

    logger.warning(
        "Without-logo final report template missing: %s — using with-logo template. "
        "Add a separate (no logo).docx at the client site for a different header/footer.",
        without_path,
    )
    return with_path


def client_template_manifest() -> list[dict[str, str]]:
    """Human-readable list of client-editable template files."""
    return [
        {"format": "CTR (form body)", "role": "body", "path": str(CTR_FORM_BODY_PATH)},
        {"format": "CTR (letterhead)", "role": "header", "path": str(CTR_LETTERHEAD_PATH)},
        {
            "format": "Protocol header/footer reference",
            "role": "header/footer",
            "path": str(PROTOCOL_HEADER_FOOTER_PATH),
        },
        {
            "format": "Protocol (Food Jaggery)",
            "role": "header/footer",
            "path": str(JAGGERY_PROTOCOL_PATH),
        },
        {
            "format": "Protocol (Food Nutrition)",
            "role": "header/footer",
            "path": str(NUTRITION_PROTOCOL_PATH),
        },
        {
            "format": "Protocol (Water)",
            "role": "header/footer",
            "path": str(WATER_PROTOCOL_PATH),
        },
        {
            "format": "Protocol (Micro)",
            "role": "header/footer",
            "path": str(MICRO_PROTOCOL_PATH),
        },
        {
            "format": "Final report with logo (Food)",
            "role": "header/footer",
            "path": str(FOOD_REPORT_WITH_LOGO_PATH),
        },
        {
            "format": "Final report without logo (Food)",
            "role": "header/footer",
            "path": str(FOOD_REPORT_WITHOUT_LOGO_PATH),
        },
        {
            "format": "Final report with logo (Water)",
            "role": "header/footer",
            "path": str(WATER_REPORT_WITH_LOGO_PATH),
        },
        {
            "format": "Final report without logo (Water)",
            "role": "header/footer",
            "path": str(WATER_REPORT_WITHOUT_LOGO_PATH),
        },
        {
            "format": "Final report with logo (Micro)",
            "role": "header/footer",
            "path": str(MICRO_REPORT_WITH_LOGO_PATH),
        },
        {
            "format": "Final report without logo (Micro)",
            "role": "header/footer",
            "path": str(MICRO_REPORT_WITHOUT_LOGO_PATH),
        },
    ]
