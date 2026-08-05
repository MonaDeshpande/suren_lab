"""
Shared brand constants for UI and generated documents.

Client site: replace assets/logo.png with the real letterhead
(keep ~7.25 x 1.42 in aspect ratio).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ORGANIZATION_NAME = "S Testing Laboratory"
LOGO_PATH = PROJECT_ROOT / "assets" / "logo.png"

# Protocol / letterhead frame from reference/Jaggery Protocol LLP.docx
LOGO_WIDTH_IN = 7.25
LOGO_HEIGHT_IN = 1.42

# Basic Nutrition house style (8.5" page, 1" margins → ~6.5" usable)
NUTRITION_PAGE_WIDTH_IN = 8.5
NUTRITION_MARGIN_IN = 1.0
NUTRITION_USABLE_WIDTH_IN = NUTRITION_PAGE_WIDTH_IN - 2 * NUTRITION_MARGIN_IN
NUTRITION_LOGO_WIDTH_IN = min(LOGO_WIDTH_IN, NUTRITION_USABLE_WIDTH_IN)
NUTRITION_LOGO_HEIGHT_IN = LOGO_HEIGHT_IN * (
    NUTRITION_LOGO_WIDTH_IN / LOGO_WIDTH_IN
)

# Blank top band in reference/Test Report Format (1).pdf (~130 pt)
TEST_REPORT_LETTERHEAD_PT = 130
