"""
services/protocol_docx.py
-------------------------
Fill the protocol Word template with header + page-1 results + appearance
+ worksheet readings + catalog formulas with worked lines and final answers.

Template layout source:
  reference/Jaggery Protocol LLP.docx

Only tests that were selected/saved for THIS sample appear in the result table.
Worksheets for every catalog test stay in the template; we fill what we can.
"""

from __future__ import annotations

import io
import logging
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from services.document_templates import (
    JAGGERY_PROTOCOL_PATH,
    MICRO_PROTOCOL_PATH,
    NUTRITION_PROTOCOL_PATH,
    PROTOCOL_HEADER_FOOTER_PATH,
    PROTOCOL_LETTERHEAD_LOGO_PATH,
    WATER_PROTOCOL_PATH,
)
from services.protocol_store import (
    ProtocolHeader,
    TestResultRow,
    format_analysis_date_range,
    format_protocol_disclaimer_paragraphs,
)
from services.samples import REPORT_FORMAT_WITHOUT_LOGO, SampleRecord, normalize_report_format
from services.input_store import primary_inputs, recalc_inputs
from services.number_format import (
    format_final_number,
    format_input_number,
    strip_analyst_label_suffix,
)
from services.protocols.test_catalog import (
    CATEGORY_WATER,
    TEST_CATALOG,
    catalog_keys_for_category,
    default_water_micro_procedure,
    get_test,
    normalize_category,
    nutrition_formula_display,
    protein_normality_key,
    protein_normality_label,
    protein_titrant_from,
    test_unsaved_display_name,
    uses_nutrition_template,
)
from services.test_packages import is_nutrition_package_type, normalize_package_type

JAGGERY_TEMPLATE_PATH = JAGGERY_PROTOCOL_PATH
WATER_TEMPLATE_PATH = WATER_PROTOCOL_PATH
NUTRITION_TEMPLATE_PATH = NUTRITION_PROTOCOL_PATH

logger = logging.getLogger(__name__)


def _protocol_layout_reference_path() -> Path:
    """Canonical client header/footer reference; falls back to nutrition template."""
    if PROTOCOL_HEADER_FOOTER_PATH.exists():
        return PROTOCOL_HEADER_FOOTER_PATH
    logger.warning(
        "Protocol header/footer reference missing: %s — using nutrition template.",
        PROTOCOL_HEADER_FOOTER_PATH,
    )
    return NUTRITION_TEMPLATE_PATH

# Legacy alias
TEMPLATE_PATH = JAGGERY_TEMPLATE_PATH

# test_key → (table_index, formula_row_indices)
# Row indices match assets/_jag_struct.txt (0-based).
WORKSHEET_FORMULAS: dict[str, tuple[int, list[int]]] = {
    "moisture": (5, [6]),
    "total_ash": (6, [6, 7]),
    "acid_insoluble_ash": (8, [6, 7]),
    "extraneous_matter": (10, [4, 5]),
    "invert_sugar": (12, [6]),
    "reducing_sugar": (12, [6]),
    "sulphated_ash": (14, [7, 8]),
    "sulphur_dioxide": (15, [2]),
}

# test_key → (table_index, [(row_idx, input_key), ...]) for Readings column
WORKSHEET_READINGS: dict[str, tuple[int, list[tuple[int, str]]]] = {
    "moisture": (
        5,
        [
            (1, "empty_dish"),
            (2, "w1"),
            (3, "w"),
            (4, "after_dry"),
            (5, "w2"),
        ],
    ),
    "total_ash": (
        6,
        [
            (1, "w1"),
            (2, "before_ign"),
            (3, "w"),
            (4, "after_ign"),
            (5, "w2"),
        ],
    ),
    "acid_insoluble_ash": (
        8,
        [
            (1, "w1"),
            (2, "before_ign"),
            (3, "w"),
            (4, "after_ign"),
            (5, "w2"),
        ],
    ),
    "extraneous_matter": (
        10,
        [
            (1, "w"),
            (2, "w2_filter"),
            (3, "w1_matter"),
        ],
    ),
    "sulphated_ash": (
        14,
        [
            (1, "w1"),
            (2, "before_ign"),
            (3, "w"),
            (4, "after_ign"),
            (5, "after_ign"),
            (6, "w2"),
        ],
    ),
    "sulphur_dioxide": (
        15,
        [
            (1, "sample_wt"),
        ],
    ),
}

# test_key → (table_index, row_idx, col_idx) for result-only worksheet cells
WORKSHEET_RESULT_CELLS: dict[str, tuple[int, int, int]] = {
    "added_color": (9, 1, 1),
}

# Shared sugar worksheet (table 12): row → (preferred_test_key, input_key)
SUGAR_READINGS: list[tuple[int, str, str]] = [
    (1, "reducing_sugar", "sample_wt"),
    (2, "reducing_sugar", "fehling_reducing"),
    (3, "reducing_sugar", "br_reducing"),
    (4, "invert_sugar", "fehling_invert"),
    (5, "invert_sugar", "br_invert"),
]

# Water protocol — table indices from reference/Water protocol 2025.docx
WATER_WORKSHEET_FORMULAS: dict[str, tuple[int, list[int]]] = {
    "tds": (4, [4, 5]),
    "chlorides": (6, [4, 5]),
    "total_alkalinity": (7, [4, 5]),
    "magnesium": (9, [1]),
    "total_hardness": (10, [4, 5]),
    "calcium_ca": (12, [4, 5]),
    "calcium_caco3": (12, [6, 7]),
}

WATER_WORKSHEET_READINGS: dict[str, tuple[int, list[tuple[int, str]]]] = {
    "odor": (3, [(1, "odor_obs")]),
    "turbidity": (3, [(2, "turbidity")]),
    "ph": (3, [(3, "ph_value")]),
    "conductivity": (3, [(4, "conductivity")]),
    "tds": (4, [(1, "w"), (2, "w1"), (3, "w2")]),
    "chlorides": (6, [(1, "v3"), (3, "n")]),
    "total_alkalinity": (7, [(1, "v"), (2, "a"), (3, "n")]),
    "total_hardness": (10, [(1, "volume"), (2, "a"), (3, "b")]),
    "calcium_ca": (12, [(1, "volume"), (2, "a"), (3, "b")]),
    "calcium_caco3": (12, [(1, "volume"), (2, "a"), (3, "c")]),
}

# Row index in water summary table 1 → test_key (row 0 is header)
WATER_SUMMARY_ROWS: dict[int, str] = {
    1: "ph",
    2: "tds",
    3: "chlorides",
    4: "total_alkalinity",
    5: "conductivity",
    6: "total_hardness",
    7: "calcium_ca",
    8: "calcium_caco3",
    9: "magnesium",
    10: "odor",
    11: "turbidity",
}

# Jaggery page-1 summary (table 2) — explicit map avoids fuzzy name collisions
# with nutrition catalog entries like "Total Sugar".
JAGGERY_SUMMARY_ROWS: dict[int, str] = {
    1: "appearance",
    2: "moisture",
    3: "total_ash",
    4: "acid_insoluble_ash",
    5: "added_color",
    6: "extraneous_matter",
    7: "invert_sugar",
    8: "reducing_sugar",
    9: "sucrose",
    10: "sulphated_ash",
    11: "sulphur_dioxide",
}

# Worksheet table groups removed when those tests were not conducted.
# Optional third element: section title substring(s) to remove with the block.
JAGGERY_PRUNE_BLOCKS: list[tuple[list[int], list[str], list[str]]] = [
    ([3, 4], ["appearance"], ["APPEARANCE"]),
    ([5], ["moisture"], ["MOISTURE"]),
    ([6], ["total_ash"], ["TOTAL ASH"]),
    ([7, 8], ["acid_insoluble_ash"], ["ASH INSOLUBLE"]),
    ([9], ["added_color"], ["ADDED COLOR"]),
    ([10], ["extraneous_matter"], ["EXTRANEOUS MATTER"]),
    ([11, 12], ["invert_sugar", "reducing_sugar", "sucrose"], ["SUGAR"]),
    ([13, 14], ["sulphated_ash"], ["SULPHATED ASH"]),
    ([15], ["sulphur_dioxide"], ["SULPHUR DIOXIDE"]),
]

NUTRITION_PRUNE_BLOCKS: list[tuple[list[int], list[str], list[str]]] = [
    ([2], ["appearance"], ["APPEARANCE"]),
    ([3], ["bn_moisture"], ["MOISTURE"]),
    ([4], ["bn_total_ash"], ["TOTAL ASH"]),
    ([5], ["bn_total_fat"], ["TOTAL FAT"]),
    ([6, 7], ["bn_protein"], ["PROTEIN"]),
    ([8], ["bn_ash_insoluble_hcl"], ["ASH INSOLUBLE"]),
    ([9], ["bn_crude_fibre"], ["CRUDE FIBRE", "FIBRE"]),
    ([10], ["bn_added_sugar", "bn_total_sugar"], ["SUGAR"]),
]

WATER_PRUNE_BLOCKS: list[tuple[list[int], list[str], list[str]]] = [
    ([3], ["odor", "turbidity", "ph", "conductivity"], []),
    ([4], ["tds"], ["TDS"]),
    ([6], ["chlorides"], ["CHLORIDE"]),
    ([7], ["total_alkalinity"], ["ALKALINITY"]),
    ([9], ["magnesium"], ["MAGNESIUM"]),
    ([10], ["total_hardness"], ["HARDNESS"]),
    ([12], ["calcium_ca", "calcium_caco3"], ["CALCIUM"]),
]

# Basic Nutrition — reference/Basic Nutrition Protocol 2026.docx
NUTRITION_WORKSHEET_FORMULAS: dict[str, tuple[int, list[int]]] = {
    "bn_moisture": (3, [7]),
    "bn_total_ash": (4, [7]),
    "bn_total_fat": (5, [4]),
    "bn_ash_insoluble_hcl": (8, [6, 7]),
    "bn_crude_fibre": (9, [4]),
    "bn_added_sugar": (10, [6]),
    "bn_total_sugar": (10, [6]),
}

# Tests whose worked math lives in body paragraphs (not worksheet table rows).
NUTRITION_PARAGRAPH_FORMULA_TESTS = frozenset(
    {"bn_protein", "bn_carbohydrate", "bn_calories"}
)

NUTRITION_WORKSHEET_READINGS: dict[str, tuple[int, list[tuple[int, str]]]] = {
    "bn_moisture": (
        3,
        [
            (1, "empty_dish"),
            (2, "w1"),
            (3, "w"),
            (4, "after_dry"),
            (5, "w2"),
        ],
    ),
    "bn_total_ash": (
        4,
        [
            (1, "w1"),
            (2, "before_ign"),
            (3, "w"),
            (4, "after_ign"),
            (5, "w2"),
        ],
    ),
    "bn_total_fat": (5, [(1, "w"), (2, "w1"), (3, "w2")]),
    "bn_protein": (
        6,
        [(1, "w"), (2, "n_naoh"), (3, "n_hcl"), (4, "br_blank"), (5, "br_sample")],
    ),
    "bn_ash_insoluble_hcl": (
        8,
        [
            (1, "w1"),
            (2, "before_ign"),
            (3, "w"),
            (4, "after_ign"),
            (5, "w2"),
        ],
    ),
    "bn_crude_fibre": (9, [(1, "w"), (2, "w1"), (3, "w2")]),
}

NUTRITION_SUGAR_READINGS: list[tuple[int, str, str]] = [
    (1, "bn_added_sugar", "sample_wt"),
    (2, "bn_added_sugar", "fehling"),
    (3, "bn_added_sugar", "br"),
    (4, "bn_total_sugar", "fehling"),
    (5, "bn_total_sugar", "br"),
]

NUTRITION_SUMMARY_ROWS: dict[int, str] = {
    1: "appearance",
    2: "bn_moisture",
    3: "bn_total_ash",
    4: "bn_total_fat",
    5: "bn_protein",
    6: "bn_carbohydrate",
    7: "bn_calories",
    8: "bn_ash_insoluble_hcl",
    9: "bn_crude_fibre",
    10: "bn_added_sugar",
    11: "bn_total_sugar",
}


def _uses_nutrition_protocol(sample: SampleRecord) -> bool:
    """
    Basic Nutrition Word template when package group is Basic or Detailed Nutrition.

    Falls back to legacy bn_* key detection when package_type is missing on old rows.
    """
    ptype = normalize_package_type(getattr(sample, "package_type", None) or "")
    if ptype:
        return is_nutrition_package_type(ptype)
    return uses_nutrition_template(sample.selected_test_keys())


def _is_nutrition_sample(sample: SampleRecord) -> bool:
    return _uses_nutrition_protocol(sample)


def _template_path(sample: SampleRecord) -> Path:
    if normalize_category(sample.category) == CATEGORY_WATER:
        return WATER_TEMPLATE_PATH
    if _uses_nutrition_protocol(sample):
        return NUTRITION_TEMPLATE_PATH
    return JAGGERY_TEMPLATE_PATH


def _worksheet_formulas_for(sample: SampleRecord) -> dict[str, tuple[int, list[int]]]:
    if normalize_category(sample.category) == CATEGORY_WATER:
        return WATER_WORKSHEET_FORMULAS
    if _uses_nutrition_protocol(sample):
        return NUTRITION_WORKSHEET_FORMULAS
    return WORKSHEET_FORMULAS


def _worksheet_readings_for(
    sample: SampleRecord,
) -> dict[str, tuple[int, list[tuple[int, str]]]]:
    if normalize_category(sample.category) == CATEGORY_WATER:
        return WATER_WORKSHEET_READINGS
    if _uses_nutrition_protocol(sample):
        return NUTRITION_WORKSHEET_READINGS
    return WORKSHEET_READINGS


def _analysis_date_display(header: ProtocolHeader) -> str:
    return format_analysis_date_range(
        header.date_of_analysis_from,
        header.date_of_analysis_to,
        legacy_single=header.date_of_analysis,
    )


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _cell_text(cell) -> str:
    """Full cell text across paragraphs (trimmed)."""
    return "\n".join(p.text for p in cell.paragraphs).strip()


def _set_cell(cell, text: str) -> None:
    """
    Replace cell text in-place, preserving first-paragraph alignment and fonts.

    Uses run-level updates instead of ``cell.text = …`` or ``paragraph.text = …``
    so template jc / rPr survive printed fill values.
    """
    text = text or ""
    if not cell.paragraphs:
        cell.text = text
        return
    _set_paragraph_text(cell.paragraphs[0], text)
    for para in cell.paragraphs[1:]:
        _set_paragraph_text(para, "")


def _set_paragraph_text(paragraph, text: str) -> None:
    """Replace a single paragraph's text, clearing extra runs."""
    text = text or ""
    if not paragraph.runs:
        paragraph.text = text
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


PROTOCOL_HEADER_FONT = ("Cambria", 10)
RESULT_TABLE_TITLE_FONT = ("Cambria", 13)
TABLE_HEADER_FONT = ("Cambria", 11)
TABLE_DATA_FONT = ("Cambria", 10)


def _apply_run_font(
    run,
    name: str,
    size_pt: float,
    *,
    bold: bool = False,
) -> None:
    """Set explicit font family, size, and optional bold on a run."""
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    for attr in (qn("w:ascii"), qn("w:hAnsi"), qn("w:cs")):
        r_fonts.set(attr, name)
    half_points = str(int(round(size_pt * 2)))
    for tag_name in ("w:sz", "w:szCs"):
        sz_el = r_pr.find(qn(tag_name))
        if sz_el is None:
            sz_el = OxmlElement(tag_name)
            r_pr.append(sz_el)
        sz_el.set(qn("w:val"), half_points)
    b_el = r_pr.find(qn("w:b"))
    if bold:
        if b_el is None:
            r_pr.append(OxmlElement("w:b"))
    elif b_el is not None:
        r_pr.remove(b_el)


def _apply_paragraph_font(
    paragraph: Paragraph,
    name: str,
    size_pt: float,
    *,
    bold: bool = False,
) -> None:
    if not paragraph.runs:
        run = paragraph.add_run(paragraph.text or "")
        if paragraph.text:
            paragraph.text = ""
    for run in paragraph.runs:
        _apply_run_font(run, name, size_pt, bold=bold)


def _apply_cell_font(
    cell,
    name: str,
    size_pt: float,
    *,
    bold: bool = False,
) -> None:
    for paragraph in cell.paragraphs:
        _apply_paragraph_font(paragraph, name, size_pt, bold=bold)


def _apply_table_font(
    table,
    name: str,
    size_pt: float,
    *,
    bold: bool = False,
) -> None:
    for row in table.rows:
        for cell in row.cells:
            _apply_cell_font(cell, name, size_pt, bold=bold)


def _apply_table_header_row_font(table, row_index: int = 0) -> None:
    name, size = TABLE_HEADER_FONT
    if row_index >= len(table.rows):
        return
    for cell in table.rows[row_index].cells:
        _apply_cell_font(cell, name, size, bold=True)


def _apply_table_data_fonts(table) -> None:
    data_name, data_size = TABLE_DATA_FONT
    for row in table.rows[1:]:
        for cell in row.cells:
            _apply_cell_font(cell, data_name, data_size)


def _apply_protocol_identity_row_fonts(row) -> None:
    name, size = PROTOCOL_HEADER_FONT
    for cell in row.cells:
        _apply_cell_font(cell, name, size)
        _set_cell_no_wrap(cell)


def _apply_water_page1_sample_row_fonts(table) -> None:
    label_name, label_size = TABLE_HEADER_FONT
    data_name, data_size = TABLE_DATA_FONT
    for row_idx in (2, 3):
        if row_idx >= len(table.rows):
            continue
        for col_idx, cell in enumerate(table.rows[row_idx].cells):
            if col_idx in (0, 4):
                _apply_cell_font(cell, label_name, label_size, bold=True)
            elif col_idx in (3, 7):
                _apply_cell_font(cell, data_name, data_size)


def _apply_sample_info_table_fonts(table) -> None:
    label_name, label_size = TABLE_HEADER_FONT
    data_name, data_size = TABLE_DATA_FONT
    for row in table.rows:
        for col_idx, cell in enumerate(row.cells):
            if col_idx in (0, 2):
                _apply_cell_font(cell, label_name, label_size, bold=True)
            else:
                _apply_cell_font(cell, data_name, data_size)


def _apply_footer_table_fonts(table) -> None:
    label_name, label_size = TABLE_HEADER_FONT
    data_name, data_size = TABLE_DATA_FONT
    for row in table.rows:
        if row.cells:
            _apply_cell_font(row.cells[0], label_name, label_size, bold=True)
        if len(row.cells) > 1:
            _apply_cell_font(row.cells[1], data_name, data_size)


def _set_cell_no_wrap(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    if tc_pr.find(qn("w:noWrap")) is None:
        tc_pr.append(OxmlElement("w:noWrap"))


def _set_table_equal_column_widths(table) -> None:
    """Give every column the same width while preserving table outer width."""
    cols = _table_grid_col_twips(table)
    if not cols:
        return
    total = sum(cols)
    count = len(cols)
    base = total // count
    widths = [base] * count
    widths[-1] += total - sum(widths)
    _replace_table_grid_columns(table, widths)


def _replace_table_grid_columns(table, col_widths: list[int]) -> None:
    if not col_widths:
        return
    target_twips = sum(col_widths)
    tbl = table._tbl
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    new_grid = OxmlElement("w:tblGrid")
    for width in col_widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        new_grid.append(col)
    tbl_pr = tbl.tblPr
    if tbl_pr is not None:
        tbl_pr.addnext(new_grid)
    else:
        tbl.insert(0, new_grid)
    for row in table.rows:
        for col_idx, cell in enumerate(row.cells):
            if col_idx >= len(col_widths):
                break
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(col_widths[col_idx]))
            tc_w.set(qn("w:type"), "dxa")
    _set_table_tbl_w(table, target_twips)


def _normalize_protocol_header_single_line(table) -> None:
    """Keep Protocol No header labels/values on one line."""
    _set_table_equal_column_widths(table)
    for row in table.rows:
        for cell in row.cells:
            _set_cell_no_wrap(cell)


def _normalize_result_table_title(doc: Document) -> None:
    for paragraph in doc.paragraphs:
        if (paragraph.text or "").strip() != "Result Table:":
            continue
        _set_paragraph_text(paragraph, "Result Table:")
        title_name, title_size = RESULT_TABLE_TITLE_FONT
        _apply_paragraph_font(paragraph, title_name, title_size, bold=True)
        return


def _page1_sample_block_table(doc: Document, sample: SampleRecord):
    if normalize_category(sample.category) == CATEGORY_WATER:
        if doc.tables and len(doc.tables[0].rows) >= 2:
            first = (doc.tables[0].rows[0].cells[0].text or "").strip().lower()
            if first.startswith("protocol no"):
                return doc.tables[0]
        return None
    for table in doc.tables:
        if _is_sample_info_table(table):
            return table
    return None


def _ensure_blank_line_before_result_table(
    doc: Document,
    sample: SampleRecord,
) -> None:
    block_table = _page1_sample_block_table(doc, sample)
    if block_table is None:
        return
    tbl_el = block_table._tbl
    next_el = tbl_el.getnext()
    if next_el is None:
        return
    if next_el.tag.endswith("p"):
        para = Paragraph(next_el, doc)
        text = (para.text or "").strip()
        if text == "Result Table:":
            blank = OxmlElement("w:p")
            tbl_el.addnext(blank)
            return
        if not text:
            following = next_el.getnext()
            if following is not None and following.tag.endswith("p"):
                following_text = (Paragraph(following, doc).text or "").strip()
                if following_text == "Result Table:":
                    return
    if next_el.tag.endswith("p") and (
        Paragraph(next_el, doc).text or ""
    ).strip() == "Result Table:":
        blank = OxmlElement("w:p")
        tbl_el.addnext(blank)


def _normalize_protocol_typography(doc: Document, sample: SampleRecord) -> None:
    """Apply Cambria typography to food- and water-protocol documents."""
    _normalize_result_table_title(doc)
    is_water = normalize_category(sample.category) == CATEGORY_WATER
    header_name, header_size = PROTOCOL_HEADER_FONT

    if is_water:
        if doc.tables:
            page1 = doc.tables[0]
            if page1.rows:
                _apply_protocol_identity_row_fonts(page1.rows[0])
            if len(page1.rows) >= 4:
                _apply_water_page1_sample_row_fonts(page1)
        for table in doc.tables[1:]:
            if _is_repeat_protocol_header_table(table):
                _apply_table_font(table, header_name, header_size)
                for row in table.rows:
                    for cell in row.cells:
                        _set_cell_no_wrap(cell)
    else:
        for section in doc.sections:
            for table in section.header.tables:
                if table.rows and len(table.rows[0].cells) >= 6:
                    _apply_table_font(table, header_name, header_size)
                    _normalize_protocol_header_single_line(table)

    for table in doc.tables:
        if _is_summary_table(table):
            _apply_table_header_row_font(table)
            _apply_table_data_fonts(table)
        elif _is_worksheet_table(table):
            _apply_table_header_row_font(table)
            _apply_table_data_fonts(table)
        elif _is_sample_info_table(table) and not is_water:
            _apply_sample_info_table_fonts(table)
        elif _is_appearance_only_table(table):
            data_name, data_size = TABLE_DATA_FONT
            _apply_table_font(table, data_name, data_size)

    if not is_water:
        for section in doc.sections:
            for table in section.footer.tables:
                _apply_footer_table_fonts(table)


def _set_row_cant_split(row) -> None:
    """Prevent a table row from splitting across pages."""
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


_WORKSHEET_CELL_MARGIN_TWIPS = 50
_WORKSHEET_CELL_SPACING_TWIPS = 40


def _set_cell_margins(cell, margin_twips: int = _WORKSHEET_CELL_MARGIN_TWIPS) -> None:
    """Inset worksheet cell text from borders (w:tcMar)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcMar"))
    if existing is not None:
        tc_pr.remove(existing)
    tc_mar = OxmlElement("w:tcMar")
    for side in ("top", "left", "bottom", "right"):
        side_el = OxmlElement(f"w:{side}")
        side_el.set(qn("w:w"), str(margin_twips))
        side_el.set(qn("w:type"), "dxa")
        tc_mar.append(side_el)
    tc_pr.append(tc_mar)


def _set_paragraph_cell_spacing(
    paragraph,
    *,
    before: int = _WORKSHEET_CELL_SPACING_TWIPS,
    after: int = _WORKSHEET_CELL_SPACING_TWIPS,
) -> None:
    """Light vertical spacing inside worksheet cells."""
    p_pr = paragraph._element.get_or_add_pPr()
    spacing = p_pr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        p_pr.append(spacing)
    spacing.set(qn("w:before"), str(before))
    spacing.set(qn("w:after"), str(after))


def _apply_worksheet_cell_padding(table) -> None:
    """Readable inset between cell borders and text on observation worksheets."""
    for row in table.rows:
        for cell in row.cells:
            _set_cell_margins(cell)
            for para in cell.paragraphs:
                _set_paragraph_cell_spacing(para)


def _make_table_inline(table) -> None:
    """Remove Word floating positioning so PDF flow matches body order."""
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        return
    floating = tbl_pr.find(qn("w:tblpPr"))
    if floating is not None:
        tbl_pr.remove(floating)


def _set_paragraph_keep_with_next(paragraph) -> None:
    """Keep paragraph with the following block (e.g. section title + table)."""
    p_pr = paragraph._element.get_or_add_pPr()
    if p_pr.find(qn("w:keepNext")) is None:
        p_pr.append(OxmlElement("w:keepNext"))


def _is_worksheet_table(table) -> bool:
    if not table.rows:
        return False
    if _is_summary_table(table):
        return False
    hdr = (table.rows[0].cells[0].text or "").lower()
    return (
        "description" in hdr
        or "sr. no" in hdr
        or "sr no" in hdr
        or "parameter" in hdr
    )


def _is_result_only_worksheet_table(table) -> bool:
    """Jaggery result-only blocks (e.g. Added Color) — 2-row, Result header, inline title."""
    if len(table.rows) != 2:
        return False
    if not _is_worksheet_table(table):
        return False
    hdr_cells = table.rows[0].cells
    if len(hdr_cells) < 2:
        return False
    hdr1 = (hdr_cells[1].text or "").strip().lower()
    if "result" in hdr1:
        return True
    label = (_cell_text(table.rows[1].cells[0]) or "").strip().lower().rstrip(":")
    known_labels = {v.lower() for v in RESULT_ONLY_ROW_LABELS.values()}
    known_titles = {
        p.lower().rstrip(":")
        for patterns in RESULT_ONLY_TITLE_PATTERNS.values()
        for p in patterns
    }
    return label in known_labels or label in known_titles


RESULT_ONLY_ROW_LABELS: dict[str, str] = {
    "added_color": "Added Color",
}

RESULT_ONLY_TITLE_PATTERNS: dict[str, list[str]] = {
    "added_color": ["ADDED COLOR"],
}


def _result_only_test_key_for_table(table, conducted: set[str]) -> str | None:
    if not _is_result_only_worksheet_table(table):
        return None
    label = (_cell_text(table.rows[1].cells[0]) or "").strip().upper().rstrip(":")
    for test_key in WORKSHEET_RESULT_CELLS:
        if test_key not in conducted:
            continue
        patterns = RESULT_ONLY_TITLE_PATTERNS.get(
            test_key, [test_key.replace("_", " ").upper()]
        )
        row_label = RESULT_ONLY_ROW_LABELS.get(
            test_key, test_key.replace("_", " ").title()
        ).upper()
        if label == row_label or any(p.rstrip(":") in label for p in patterns):
            return test_key
    return None


def _promote_inline_worksheet_section_titles(
    doc: Document,
    conducted: set[str],
) -> None:
    """Move inline section titles (e.g. ADDED COLOR:) to body paragraphs above the table."""
    for table in list(doc.tables):
        test_key = _result_only_test_key_for_table(table, conducted)
        if not test_key:
            continue
        row_label_cell = table.rows[1].cells[0]
        title_text = (_cell_text(row_label_cell) or "").strip()
        if not title_text:
            continue
        if not title_text.endswith(":"):
            title_text = f"{title_text}:"
        _insert_paragraph_before(doc, table._tbl, title_text)
        row_label = RESULT_ONLY_ROW_LABELS.get(
            test_key, test_key.replace("_", " ").title()
        )
        _set_cell(row_label_cell, row_label)


def _is_repeat_protocol_header_table(table) -> bool:
    if len(table.rows) != 1:
        return False
    first = (table.rows[0].cells[0].text or "").strip()
    return first.startswith("Protocol No")


def _paragraph_before_table(doc: Document, table) -> Paragraph | None:
    prev = table._tbl.getprevious()
    while prev is not None:
        if prev.tag.endswith("p"):
            return Paragraph(prev, doc)
        if prev.tag.endswith("tbl"):
            break
        prev = prev.getprevious()
    return None


def _section_title_paragraph_before_table(
    doc: Document,
    table,
    title_patterns: list[str],
) -> Paragraph | None:
    """Walk back past blank spacer paragraphs to find the section title."""
    prev = table._tbl.getprevious()
    while prev is not None:
        if prev.tag.endswith("tbl"):
            break
        if prev.tag.endswith("p"):
            para = Paragraph(prev, doc)
            text = (para.text or "").strip()
            if text and _title_matches(text, title_patterns):
                return para
        prev = prev.getprevious()
    return None


def _delete_paragraph(paragraph: Paragraph) -> None:
    el = paragraph._element
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _title_matches(text: str, patterns: list[str]) -> bool:
    upper = text.upper()
    return any(p.upper() in upper for p in patterns)


def _suffix_unit(value: str, unit: str) -> str:
    """Append a unit suffix when the worked value does not already include it."""
    val = (value or "").strip()
    u = (unit or "").strip()
    if not val:
        return val
    if not u:
        return val
    if val.endswith(u) or val.endswith(f" {u}"):
        return val
    return f"{val} {u}"


def _formula_readings_text(
    worked_line: str,
    answer: str,
    unit: str,
    *,
    is_final_row: bool,
    is_dual_first_row: bool,
) -> str:
    """Build Readings column: worked calculation + answer with unit."""
    del is_dual_first_row  # wet-row result is already on worked_line after "="
    parts: list[str] = []
    if worked_line:
        parts.append(_format_worksheet_reading_line(worked_line))
    if is_final_row and answer:
        tail = (
            worked_line.rsplit("=", 1)[-1].strip()
            if worked_line and "=" in worked_line
            else ""
        )
        ans_val = answer.split()[0] if answer else ""
        if ans_val and tail.replace("%", "").strip() != ans_val:
            parts.append(_format_worksheet_reading_line(answer))
        elif not worked_line:
            parts.append(_format_worksheet_reading_line(answer))
    return "\n".join(parts)


def _fill_sugar_formula_row(
    row,
    by_key: dict[str, TestResultRow],
    ctx: dict[str, float],
) -> None:
    """Jaggery sugar table row: symbolic then calculations (merged or split cells)."""
    if not row.cells:
        return

    merged = (
        len(row.cells) >= 3
        and row.cells[0]._tc is row.cells[2]._tc
    )
    symbolic_parts: list[str] = []
    reading_parts: list[str] = []

    if "invert_sugar" in by_key:
        res = by_key["invert_sugar"]
        inputs = res.inputs or {}
        symbolic_parts.append(
            "Total Invert sugar(On dry basis)% =\n"
            "Concentration of sugar in g X 250 X 100\n"
            "Wt. of sample taken in g X B.R. of Fehling solution"
        )
        for line in worked_formula_lines(
            "invert_sugar", inputs, ctx, res.result_value or ""
        ):
            reading_parts.append(line)
        ans = _answer_text(res)
        if ans:
            reading_parts.append(ans)

    if "reducing_sugar" in by_key:
        res = by_key["reducing_sugar"]
        inputs = res.inputs or {}
        symbolic_parts.append(
            "Total reducing sugar % =\n"
            "Concentration of sugar in g X 250 X 10\n"
            "Wt. of sample taken in g X B.R. of Fehling solution"
        )
        for line in worked_formula_lines(
            "reducing_sugar", inputs, ctx, res.result_value or ""
        ):
            reading_parts.append(line)
        ans = _answer_text(res)
        if ans:
            reading_parts.append(ans)

    sucrose_res = by_key.get("sucrose")
    if sucrose_res or (
        "invert_sugar" in by_key and "reducing_sugar" in by_key
    ):
        inputs = (sucrose_res.inputs if sucrose_res else {}) or {}
        result_value = sucrose_res.result_value if sucrose_res else ""
        if not result_value and "invert_sugar" in ctx and "reducing_sugar" in ctx:
            derived = (ctx["invert_sugar"] - ctx["reducing_sugar"]) * 0.95
            result_value = _fmt_num(derived, 2)
        symbolic_parts.append(
            "Sucrose(On dry basis)% =\nInvert sugar - Reducing sugar X 0.95"
        )
        for line in worked_formula_lines("sucrose", inputs, ctx, result_value):
            reading_parts.append(line)
        if sucrose_res:
            ans = _answer_text(sucrose_res)
            if ans:
                reading_parts.append(ans)
        elif result_value:
            reading_parts.append(f"{result_value} %")

    if merged:
        merged_text = "\n\n".join(symbolic_parts)
        if reading_parts:
            merged_text += "\n\n" + "\n\n".join(reading_parts)
        _set_cell(row.cells[0], merged_text)
        return

    if len(row.cells) < 3:
        _fill_sugar_formula_cell(row.cells[0], by_key, ctx)
        return

    if symbolic_parts:
        _set_cell(row.cells[0], "\n\n".join(symbolic_parts))
    if reading_parts:
        _set_cell(row.cells[2], "\n\n".join(reading_parts))


def _fill_sugar_formula_cell(cell, by_key: dict[str, TestResultRow], ctx: dict[str, float]) -> None:
    """
    Fill Invert / Reducing / Sucrose into the separate paragraph slots of
    table-12 formula row (matches Jaggery Protocol LLP.docx layout).

    Template cell paragraphs (approx):
      P0–P1  Invert symbolic formula (×100)
      P2     Invert worked line / answer
      P7–P8  Reducing symbolic formula (×10)
      P9     Reducing worked line / answer
      P14    Sucrose symbolic formula (×0.95)
      P15    Sucrose worked line / answer
      P19    Concentration-of-sugar note (leave as-is)
    """
    paras = cell.paragraphs
    if len(paras) < 15:
        # Fallback: single-block fill if template shape differs
        blocks: list[str] = []
        for k, label in (
            ("invert_sugar", "Invert"),
            ("reducing_sugar", "Reducing"),
            ("sucrose", "Sucrose"),
        ):
            if k not in by_key and k != "sucrose":
                continue
            if k == "sucrose" and k not in by_key and not (
                "invert_sugar" in by_key and "reducing_sugar" in by_key
            ):
                continue
            test = TEST_CATALOG.get(k)
            res = by_key.get(k)
            if not test:
                continue
            inputs = (res.inputs if res else {}) or {}
            result_value = res.result_value if res else ""
            blocks.append(f"{label}: {test.formula_display}")
            for worked in worked_formula_lines(k, inputs, ctx, result_value or ""):
                blocks.append(worked)
            if res and (res.result_value or "").strip():
                blocks.append(f"{label} answer: {_answer_text(res)}")
        if blocks:
            _set_cell(cell, "\n".join(blocks))
        return

    # Invert
    if "invert_sugar" in by_key:
        res = by_key["invert_sugar"]
        inputs = res.inputs or {}
        _set_paragraph_text(
            paras[0],
            "Total Invert sugar(On dry basis)% =\t"
            "Concentration of sugar in g X 250 X 100",
        )
        _set_paragraph_text(
            paras[1],
            "Wt. of sample taken in g X B.R. of Fehling solution",
        )
        worked = worked_formula_lines(
            "invert_sugar", inputs, ctx, res.result_value or ""
        )
        ans = _answer_text(res)
        line = "\n".join(worked) if worked else ""
        if ans:
            line = f"{line}\nInvert answer: {ans}".strip()
        if len(paras) > 2:
            _set_paragraph_text(paras[2], line)

    # Reducing
    if "reducing_sugar" in by_key:
        res = by_key["reducing_sugar"]
        inputs = res.inputs or {}
        _set_paragraph_text(
            paras[7],
            "Total reducing sugar % =\t"
            "Concentration of sugar in g X 250 X 10",
        )
        if len(paras) > 8:
            _set_paragraph_text(
                paras[8],
                "Wt. of sample taken in g X B.R. of Fehling solution",
            )
        worked = worked_formula_lines(
            "reducing_sugar", inputs, ctx, res.result_value or ""
        )
        ans = _answer_text(res)
        line = "\n".join(worked) if worked else ""
        if ans:
            line = f"{line}\nReducing answer: {ans}".strip()
        if len(paras) > 9:
            _set_paragraph_text(paras[9], line)

    # Sucrose — fill when sucrose saved, or both parent sugars present
    sucrose_res = by_key.get("sucrose")
    if sucrose_res or (
        "invert_sugar" in by_key and "reducing_sugar" in by_key
    ):
        inputs = (sucrose_res.inputs if sucrose_res else {}) or {}
        result_value = sucrose_res.result_value if sucrose_res else ""
        if not result_value and "invert_sugar" in ctx and "reducing_sugar" in ctx:
            # Derive display if only parents were saved
            derived = (ctx["invert_sugar"] - ctx["reducing_sugar"]) * 0.95
            result_value = _fmt_num(derived, 2)
        _set_paragraph_text(
            paras[14],
            "Sucrose(On dry basis)% =\t"
            "Invert sugar - Reducing sugar X 0.95",
        )
        worked = worked_formula_lines("sucrose", inputs, ctx, result_value)
        ans = ""
        if sucrose_res:
            ans = _answer_text(sucrose_res)
        elif result_value:
            ans = f"{result_value} %"
        line = "\n".join(worked) if worked else ""
        if ans:
            line = f"{line}\nSucrose answer: {ans}".strip()
        if len(paras) > 15:
            _set_paragraph_text(paras[15], line)


def _formula_lines(formula_display: str) -> list[str]:
    """Split dual formulas on ';' into one line per worksheet row."""
    parts = [p.strip() for p in (formula_display or "").split(";")]
    return [_format_worksheet_formula_description(p) for p in parts if p]


def _format_worksheet_formula_description(symbolic: str) -> str:
    """Break long dry-basis formulas so (100 − Moisture) stays on one line."""
    text = (symbolic or "").strip()
    if not text:
        return text
    text = _format_worksheet_reading_line(text)
    if " = " in text and "moisture" in text.lower():
        label, rhs = text.split(" = ", 1)
        return f"{label} =\n{rhs.strip()}"
    return text


def _format_worksheet_reading_line(text: str) -> str:
    """Keep (100 − Moisture) on one line in worksheet Readings cells."""
    if not text:
        return text
    nb_moisture = "(100\u00a0−\u00a0Moisture)"
    out = text.replace("(100 − Moisture)", nb_moisture)
    out = out.replace("(100 - Moisture)", nb_moisture)
    out = re.sub(
        r"\(100\s*-\s*([Mm]oisture)\)",
        lambda m: f"(100\u00a0−\u00a0{m.group(1)})",
        out,
    )
    return out


def _fmt_num(value: Any, places: int = 4) -> str:
    """Format a numeric input/result for the worksheet."""
    return format_input_number(value, max_places=places)


def _input_num(inputs: dict[str, Any], key: str) -> Optional[float]:
    raw = inputs.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _moisture_from(inputs: dict[str, Any], ctx: dict[str, float]) -> Optional[float]:
    if str(inputs.get("moisture_pct") or "").strip():
        val = _input_num(inputs, "moisture_pct")
        if val is not None:
            return val
    if ctx.get("moisture") is not None:
        try:
            return float(ctx["moisture"])
        except (TypeError, ValueError):
            pass
    if ctx.get("bn_moisture") is not None:
        try:
            return float(ctx["bn_moisture"])
        except (TypeError, ValueError):
            pass
    return None


def _result_context(by_key: dict[str, TestResultRow]) -> dict[str, float]:
    ctx: dict[str, float] = {}
    for key, row in by_key.items():
        if row.result_numeric is not None:
            ctx[key] = float(row.result_numeric)
    return ctx


def _answer_text(res: TestResultRow) -> str:
    value = (res.result_value or "").strip()
    if not value:
        return ""
    unit = (res.unit or "").strip()
    if unit and not value.endswith(unit):
        return f"{value} {unit}"
    return value


def _answer_from_value(value: str, unit: str) -> str:
    val = (value or "").strip()
    if not val:
        return ""
    u = (unit or "").strip()
    if u and not val.endswith(u):
        return f"{val} {u}"
    return val


def _protocol_issued_to(sample: SampleRecord, header: ProtocolHeader) -> str:
    """Sample Issued to: analyst full name without legacy picker suffix."""
    name = (sample.assigned_analyst_name or "").strip()
    if name:
        return strip_analyst_label_suffix(name)
    return strip_analyst_label_suffix(header.issued_to or "")


def _protocol_issued_by_display(issued_by: str | None) -> str:
    """Issuer name for printed protocol; omit audit fallback 'system'."""
    name = (issued_by or "").strip()
    if name.lower() == "system":
        return ""
    return name


def _fill_water_issued_by_cell(cell, issuer: str | None) -> None:
    """Preserve template label in merged 'Sample Issued by' cell; append issuer below."""
    existing = _cell_text(cell)
    base = existing.strip() if existing.strip() else "Sample Issued by"
    if "sample issued" not in base.lower():
        base = "Sample Issued by"
    name = _protocol_issued_by_display(issuer)
    if name:
        _set_cell(cell, f"{base.rstrip()}\n{name}")
    else:
        _set_cell(cell, base.rstrip())


def _water_sample_includes_micro(sample: SampleRecord) -> bool:
    from services.protocols.test_catalog import WATER_MICRO_TEST_KEYS

    selected = set(sample.selected_test_keys())
    return bool(selected & set(WATER_MICRO_TEST_KEYS))


def _remove_orphan_page_break_paragraphs(doc: Document) -> None:
    """Drop empty paragraphs that only force a page break (common after table prune)."""
    body = doc.element.body
    for child in list(body):
        if child.tag.endswith("p") and _paragraph_is_page_break_only(child):
            parent = child.getparent()
            if parent is not None:
                parent.remove(child)


def _computed_result_value(
    test,
    test_key: str,
    inputs: dict[str, Any],
    ctx: dict[str, float],
) -> str:
    if not test or not inputs:
        return ""
    local_ctx = dict(ctx)
    local_ctx.pop(test_key, None)
    try:
        display, numeric = test.calculate(inputs, local_ctx)
        if numeric is not None:
            return format_final_number(numeric)
        return (display or "").strip()
    except (ValueError, TypeError):
        return ""


def _fill_input_reading_cells(
    row,
    col: int,
    inputs: dict[str, Any],
    test_key: str,
    input_key: str,
) -> None:
    primary = primary_inputs(inputs)
    recalc = recalc_inputs(inputs)
    unit = _input_field_unit(test_key, input_key)
    p_raw = primary.get(input_key)
    if p_raw is not None and str(p_raw).strip():
        _set_reading_cell(row, col, _format_reading_text(p_raw, unit))
    r_raw = recalc.get(input_key)
    recalc_col = col + 1
    if (
        r_raw is not None
        and str(r_raw).strip()
        and recalc_col < len(row.cells)
    ):
        _set_reading_cell(row, recalc_col, _format_reading_text(r_raw, unit))


def _input_field_unit(test_key: str, input_key: str) -> str:
    """Unit label from the catalog input field, if any."""
    test = TEST_CATALOG.get(test_key)
    if not test:
        return ""
    for field in test.inputs:
        if field.key == input_key:
            return (field.unit or "").strip()
    return ""


def _format_reading_text(raw: Any, unit: str = "") -> str:
    """Format a saved reading for the worksheet (value, optionally with unit)."""
    if raw is None or str(raw).strip() == "":
        return ""
    try:
        float(raw)
        text = _fmt_num(raw)
    except (TypeError, ValueError):
        text = str(raw).strip()
    u = (unit or "").strip()
    if u and not text.endswith(u):
        return f"{text} {u}"
    return text


def _set_reading_cell(row, reading_col: int, text: str) -> None:
    """
    Write a reading into the Readings column.

    Jaggery/nutrition worksheets often have Description | value | bare unit (g).
    Put value+unit in the value cell and clear a sibling bare-unit cell so the
    number stays visible next to a lone 'g'.
    """
    if not text or not row.cells or reading_col >= len(row.cells):
        return
    text = _format_worksheet_reading_line(text)
    _set_cell(row.cells[reading_col], text)
    _set_cell_no_wrap(row.cells[reading_col])
    # Clear adjacent bare unit cell when value already includes the unit
    for sibling in (reading_col + 1, reading_col - 1):
        if sibling < 0 or sibling >= len(row.cells) or sibling == 0:
            continue
        sibling_text = (row.cells[sibling].text or "").strip()
        if sibling_text in ("g", "ml", "%", "ppm", "—", "-"):
            _set_cell(row.cells[sibling], "")


def _set_result_cell(row, text: str) -> None:
    """Write answer into the Readings/% column (prefer cells[1], else cells[2])."""
    if not text or not row.cells:
        return
    if len(row.cells) >= 2:
        _set_cell(row.cells[1], text)
    elif len(row.cells) >= 3:
        _set_cell(row.cells[2], text)


def worked_formula_lines(
    test_key: str,
    inputs: dict[str, Any],
    ctx: dict[str, float],
    result_value: str,
) -> list[str]:
    """
    One worked (numbers plugged in) line per symbolic formula_display segment.

    Mirrors calculator math in test_catalog so dual-line ash/sugar rows stay consistent.
    """
    ans = (result_value or "").strip()
    try:
        if test_key == "moisture":
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            w = _input_num(inputs, "w")
            if None in (w1, w2, w) or w == 0:
                return []
            worked = (
                f"({_fmt_num(w1)} - {_fmt_num(w2)}) × 100 / {_fmt_num(w)} "
                f"= {_suffix_unit(ans, '%')}"
            )
            return [worked]

        if test_key in ("total_ash", "acid_insoluble_ash", "sulphated_ash"):
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            w = _input_num(inputs, "w")
            moisture = _moisture_from(inputs, ctx)
            if None in (w1, w2, w) or w == 0 or moisture is None:
                return []
            wet = (w2 - w1) * 100.0 / w
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            wet_line = (
                f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 100 / {_fmt_num(w)} "
                f"= {_suffix_unit(_fmt_num(wet, 2), '%')}"
            )
            dry_line = _format_worksheet_reading_line(
                f"{_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                f"= {_suffix_unit(ans or _fmt_num(dry, 2), '%')}"
            )
            return [wet_line, dry_line]

        if test_key == "extraneous_matter":
            w = _input_num(inputs, "w")
            w2 = _input_num(inputs, "w2_filter")
            w1 = _input_num(inputs, "w1_matter")
            moisture = _moisture_from(inputs, ctx)
            if None in (w, w1, w2) or w == 0 or moisture is None:
                return []
            wet = (w1 - w2) * 100.0 / w
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            wet_line = (
                f"({_fmt_num(w1)} - {_fmt_num(w2)}) × 100 / {_fmt_num(w)} "
                f"= {_suffix_unit(_fmt_num(wet, 2), '%')}"
            )
            dry_line = _format_worksheet_reading_line(
                f"{_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                f"= {_suffix_unit(ans or _fmt_num(dry, 2), '%')}"
            )
            return [wet_line, dry_line]

        if test_key == "invert_sugar":
            conc = _input_num(inputs, "sugar_conc")
            wt = _input_num(inputs, "sample_wt")
            br = _input_num(inputs, "br_invert")
            moisture = _moisture_from(inputs, ctx)
            if None in (conc, wt, br) or wt == 0 or br == 0:
                return []
            wet = conc * 250.0 * 100.0 / (wt * br)
            wet_line = (
                f"{_fmt_num(conc)} × 250 × 100 / ({_fmt_num(wt)} × {_fmt_num(br)}) "
                f"= {_fmt_num(wet, 2)}"
            )
            if moisture is None:
                return [wet_line] if not ans else [wet_line, f"= {ans} % Dwt.b."]
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            dry_line = (
                f"{_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                f"= {ans or _fmt_num(dry, 2)} % Dwt.b."
            )
            return [wet_line, dry_line]

        if test_key == "reducing_sugar":
            conc = _input_num(inputs, "sugar_conc")
            wt = _input_num(inputs, "sample_wt")
            br = _input_num(inputs, "br_reducing")
            moisture = _moisture_from(inputs, ctx)
            if None in (conc, wt, br) or wt == 0 or br == 0:
                return []
            wet = conc * 250.0 * 10.0 / (wt * br)
            wet_line = (
                f"{_fmt_num(conc)} × 250 × 10 / ({_fmt_num(wt)} × {_fmt_num(br)}) "
                f"= {_fmt_num(wet, 2)}"
            )
            if moisture is None:
                return [wet_line] if not ans else [wet_line, f"= {ans} % Dwt.b."]
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            dry_line = (
                f"{_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                f"= {ans or _fmt_num(dry, 2)} % Dwt.b."
            )
            return [wet_line, dry_line]

        if test_key == "sucrose":
            inv = ctx.get("invert_sugar")
            red = ctx.get("reducing_sugar")
            if inv is None:
                inv = _input_num(inputs, "invert_dry")
            if red is None:
                red = _input_num(inputs, "reducing_dry")
            if inv is None or red is None:
                return []
            return [
                (
                    f"({_fmt_num(inv, 2)} - {_fmt_num(red, 2)}) × 0.95 "
                    f"= {_suffix_unit(ans or _fmt_num((inv - red) * 0.95, 2), '%')}"
                )
            ]

        if test_key == "sulphur_dioxide":
            ug = _input_num(inputs, "ug_so4")
            wt = _input_num(inputs, "sample_wt")
            if None in (ug, wt) or wt == 0:
                return []
            return [
                f"({_fmt_num(ug)} × 10) / {_fmt_num(wt)} "
                f"= {_suffix_unit(ans, 'ppm')}"
            ]

        if test_key == "tds":
            w = _input_num(inputs, "w")
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            if None in (w, w1, w2) or w == 0:
                return []
            return [
                f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 1000 × 1000 / {_fmt_num(w)} = {ans}"
            ]

        if test_key == "chlorides":
            v3 = _input_num(inputs, "v3")
            v1 = _input_num(inputs, "v1")
            v2 = _input_num(inputs, "v2")
            n = _input_num(inputs, "n")
            if None in (v3, v1, v2, n) or v3 == 0:
                return []
            worked = (v1 - v2) * n * 35.45 * 1000.0 / v3
            return [
                f"({_fmt_num(v1)} - {_fmt_num(v2)}) × {_fmt_num(n)} × 35.45 × 1000 / "
                f"{_fmt_num(v3)} = {ans or _fmt_num(worked, 1)}"
            ]

        if test_key == "total_alkalinity":
            v = _input_num(inputs, "v")
            a = _input_num(inputs, "a")
            n = _input_num(inputs, "n")
            if None in (v, a, n) or v == 0:
                return []
            worked = a * n * 50000.0 / v
            return [f"{_fmt_num(a)} × {_fmt_num(n)} × 50000 / {_fmt_num(v)} = {ans or _fmt_num(worked, 1)}"]

        if test_key in ("total_hardness", "calcium_ca"):
            volume = _input_num(inputs, "volume")
            a = _input_num(inputs, "a")
            b = _input_num(inputs, "b")
            if None in (volume, a, b) or volume == 0:
                return []
            worked = a * b * 1000.0 / volume
            return [
                f"{_fmt_num(a)} × {_fmt_num(b)} × 1000 / {_fmt_num(volume)} = {ans or _fmt_num(worked, 1)}"
            ]

        if test_key == "calcium_caco3":
            volume = _input_num(inputs, "volume")
            a = _input_num(inputs, "a")
            c = _input_num(inputs, "c")
            if None in (volume, a, c) or volume == 0:
                return []
            worked = a * c * 1000.0 / volume
            return [
                f"{_fmt_num(a)} × {_fmt_num(c)} × 1000 / {_fmt_num(volume)} = {ans or _fmt_num(worked, 1)}"
            ]

        if test_key == "magnesium":
            hardness = ctx.get("total_hardness")
            calcium = ctx.get("calcium_caco3")
            if hardness is None:
                hardness = _input_num(inputs, "total_hardness")
            if calcium is None:
                calcium = _input_num(inputs, "calcium_caco3")
            if hardness is None or calcium is None:
                return []
            worked = (hardness - calcium) * 0.243
            return [
                f"({_fmt_num(hardness, 1)} - {_fmt_num(calcium, 1)}) × 0.243 "
                f"= {ans or _fmt_num(worked, 1)}"
            ]

        if test_key == "bn_moisture":
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            w = _input_num(inputs, "w")
            if None in (w1, w2, w) or w == 0:
                return []
            return [f"({_fmt_num(w1)} - {_fmt_num(w2)}) × 100 / {_fmt_num(w)} = {ans}"]

        if test_key == "bn_total_ash":
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            w = _input_num(inputs, "w")
            if None in (w1, w2, w) or w == 0:
                return []
            return [f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 100 / {_fmt_num(w)} = {ans}"]

        if test_key == "bn_total_fat":
            w = _input_num(inputs, "w")
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            if None in (w, w1, w2) or w == 0:
                return []
            return [f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 100 / {_fmt_num(w)} = {ans}"]

        if test_key == "bn_protein":
            from services.protocols.test_catalog import protein_formula_display

            w = _input_num(inputs, "w")
            titrant = protein_titrant_from(inputs)
            norm_key = protein_normality_key(titrant)
            n_titrant = _input_num(inputs, norm_key)
            br_blank = _input_num(inputs, "br_blank")
            br_sample = _input_num(inputs, "br_sample")
            n_factor = _input_num(inputs, "n_factor")
            if None in (w, n_titrant, br_blank, br_sample, n_factor) or w == 0:
                return []
            nitrogen = 0.014 * n_titrant * (br_blank - br_sample) * 100.0 / w
            protein = nitrogen * n_factor
            norm_label = protein_normality_label(titrant)
            symbolic = protein_formula_display(titrant)
            nitrogen_line = (
                f"{symbolic.split(';')[0].strip()}\n"
                f"0.014 × {_fmt_num(n_titrant)} (N({norm_label})) × "
                f"({_fmt_num(br_blank)} - {_fmt_num(br_sample)}) × 100 / {_fmt_num(w)} "
                f"= {_fmt_num(nitrogen, 2)}"
            )
            protein_line = (
                f"{_fmt_num(nitrogen, 2)} × {_fmt_num(n_factor)} "
                f"= {ans or _fmt_num(protein, 2)}"
            )
            return [nitrogen_line, protein_line]

        if test_key == "bn_ash_insoluble_hcl":
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            w = _input_num(inputs, "w")
            moisture = ctx.get("bn_moisture")
            if moisture is None:
                moisture = _input_num(inputs, "moisture_pct")
            if None in (w1, w2, w) or w == 0 or moisture is None:
                return []
            wet = (w2 - w1) * 100.0 / w
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            wet_line = (
                f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 100 / {_fmt_num(w)} "
                f"= {_fmt_num(wet, 2)}"
            )
            dry_line = (
                f"{_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                f"= {ans or _fmt_num(dry, 2)}"
            )
            return [wet_line, dry_line]

        if test_key == "bn_crude_fibre":
            w = _input_num(inputs, "w")
            w1 = _input_num(inputs, "w1")
            w2 = _input_num(inputs, "w2")
            if None in (w, w1, w2) or w == 0:
                return []
            return [f"({_fmt_num(w2)} - {_fmt_num(w1)}) × 100 / {_fmt_num(w)} = {ans}"]

        if test_key in ("bn_added_sugar", "bn_total_sugar"):
            factor = 10.0 if test_key == "bn_added_sugar" else 100.0
            conc = _input_num(inputs, "sugar_conc")
            wt = _input_num(inputs, "sample_wt")
            br = _input_num(inputs, "br")
            moisture = ctx.get("bn_moisture")
            if moisture is None:
                moisture = _input_num(inputs, "moisture_pct")
            if None in (conc, wt, br) or wt == 0 or br == 0 or moisture is None:
                return []
            wet = conc * 250.0 * factor / (wt * br)
            dry = wet * 100.0 / (100.0 - moisture) if (100.0 - moisture) != 0 else None
            fac_label = "10" if factor == 10.0 else "100"
            return [
                (
                    f"{_fmt_num(conc)} × 250 × {fac_label} / ({_fmt_num(wt)} × {_fmt_num(br)}) "
                    f"= {_fmt_num(wet, 2)}; "
                    f"dry {_fmt_num(wet, 2)} × 100 / (100 - {_fmt_num(moisture, 2)}) "
                    f"= {ans or _fmt_num(dry, 2)}"
                )
            ]

        if test_key == "bn_carbohydrate":
            moisture = ctx.get("bn_moisture")
            protein = ctx.get("bn_protein")
            fat = ctx.get("bn_total_fat")
            ash = ctx.get("bn_total_ash")
            for key, val in (
                ("moisture_pct", moisture),
                ("protein_pct", protein),
                ("fat_pct", fat),
                ("ash_pct", ash),
            ):
                if val is None:
                    val = _input_num(inputs, key)
                if key == "moisture_pct":
                    moisture = val
                elif key == "protein_pct":
                    protein = val
                elif key == "fat_pct":
                    fat = val
                else:
                    ash = val
            if None in (moisture, protein, fat, ash):
                return []
            worked = 100.0 - moisture - protein - fat - ash
            return [
                f"100 - {_fmt_num(moisture, 2)} - {_fmt_num(protein, 2)} - "
                f"{_fmt_num(fat, 2)} - {_fmt_num(ash, 2)} "
                f"= {ans or _fmt_num(worked, 2)}"
            ]

        if test_key == "bn_calories":
            protein = ctx.get("bn_protein")
            carb = ctx.get("bn_carbohydrate")
            fat = ctx.get("bn_total_fat")
            if protein is None:
                protein = _input_num(inputs, "protein_pct")
            if carb is None:
                carb = _input_num(inputs, "carb_pct")
            if fat is None:
                fat = _input_num(inputs, "fat_pct")
            if None in (protein, carb, fat):
                return []
            worked = 4.0 * (protein + carb) + 9.0 * fat
            return [
                f"4×({_fmt_num(protein, 2)}+{_fmt_num(carb, 2)}) + 9×{_fmt_num(fat, 2)} "
                f"= {ans or _fmt_num(worked, 1)}"
            ]

        if test_key.startswith("custom_"):
            from services.custom_formulas import get_formula, load_custom_lab_tests
            from services.formula_eval import substitute_and_format

            test = load_custom_lab_tests().get(test_key)
            if test is None:
                return []
            formula_id = int(test_key.replace("custom_", ""))
            rec = get_formula(formula_id)
            if rec is None:
                return []
            field_keys = [i.field_key for i in rec.inputs]
            line = substitute_and_format(
                rec.expression,
                inputs,
                field_keys,
                ans,
            )
            return [line] if line else []
    except (TypeError, ValueError, ZeroDivisionError):
        return []
    return []


def _clear_paragraph_drawings(paragraph) -> None:
    """Remove DrawingML / VML shapes from a header paragraph."""
    p = paragraph._p
    for tag in ("w:drawing", "w:pict"):
        for el in p.findall(".//" + qn(tag)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)


def _clear_cell_drawings(cell) -> None:
    """Remove DrawingML / VML shapes from every paragraph in a table cell."""
    for paragraph in cell.paragraphs:
        _clear_paragraph_drawings(paragraph)


def _blank_director_approval(doc: Document) -> None:
    """
    Strip hardcoded director name/signature from protocol footers.

    Water / Basic Nutrition templates embed \"Dr. Surendra Nashikkar\" plus a
    signature image in the Approved-by footer. Leave the label blank for
    pen/sign at the client site.
    """
    markers = ("surendra", "nashikkar", "nashikar")
    for section in doc.sections:
        footer = section.footer
        for table in footer.tables:
            for row in table.rows:
                for cell in row.cells:
                    lower = (cell.text or "").lower()
                    if any(m in lower for m in markers) or "director" in lower:
                        _clear_cell_drawings(cell)
                        _set_cell(cell, "")
            for row in table.rows:
                cell_texts = [(cell, (cell.text or "")) for cell in row.cells]
                row_lower = " ".join(t for _, t in cell_texts).lower()
                if "approved" not in row_lower and not any(
                    m in row_lower for m in markers
                ):
                    continue
                for cell, text in cell_texts:
                    lower = text.lower()
                    if "approved" in lower and not any(m in lower for m in markers):
                        _clear_cell_drawings(cell)
                        if "reviewed" in lower and "issued" not in lower:
                            _set_cell(cell, "Reviewed & Approved by:")
                        elif "reviewed" in lower and "issued" in lower:
                            _set_cell(cell, "Reviewed & Issued by:")
                        else:
                            _set_cell(cell, "Approved by:")
                        continue
                    if any(m in lower for m in markers) or "director" in lower:
                        _clear_cell_drawings(cell)
                        _set_cell(cell, "")
                        continue
                    if "prepared" not in lower and "reviewed" not in lower:
                        _clear_cell_drawings(cell)
                        if not any(
                            lab in lower for lab in ("prepared by", "reviewed")
                        ):
                            _set_cell(cell, "")
        for paragraph in footer.paragraphs:
            raw = paragraph.text or ""
            if any(m in raw.lower() for m in markers):
                _clear_paragraph_drawings(paragraph)
                _set_paragraph_text(paragraph, "")


def _nutrition_footer_table_xml():
    """Clone the protocol reference approval footer table (Prepared / Reviewed / Approved)."""
    ref_path = _protocol_layout_reference_path()
    if not ref_path.exists():
        return None
    ref = Document(str(ref_path))
    if not ref.sections[0].footer.tables:
        return None
    return deepcopy(ref.sections[0].footer.tables[0]._tbl)


def _apply_standard_protocol_footer(doc: Document) -> None:
    """Replace all section footers with the Basic Nutrition approval table."""
    footer_tbl = _nutrition_footer_table_xml()
    if footer_tbl is None:
        return
    for section in doc.sections:
        footer_el = section.footer._element
        for child in list(footer_el):
            footer_el.remove(child)
        footer_el.append(deepcopy(footer_tbl))


def _is_body_signature_paragraph(text: str) -> bool:
    """True for template body signature lines (not footer approval rows)."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    first = _strip_section_title_number(stripped.split("\n", 1)[0])
    lower = first.lower()
    if lower.startswith("analyzed by") or lower.startswith("analysed by"):
        return True
    if lower.startswith("checked by"):
        return True
    if "technical manager" in lower:
        return True
    if lower.startswith("dated signature"):
        return True
    if first.startswith("Name") and "technical manager" in lower:
        return True
    return False


def _remove_body_signature_blocks(doc: Document) -> None:
    """Remove Analyzed By / Checked By body blocks from all protocol templates."""
    for paragraph in list(doc.paragraphs):
        if _is_body_signature_paragraph(paragraph.text or ""):
            _delete_paragraph(paragraph)


def _signature_reference_layout() -> tuple[list[Any], int]:
    """Clone signature paragraph XML and line width from the nutrition template."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return [], 115
    ref = Document(str(NUTRITION_TEMPLATE_PATH))
    paras = [deepcopy(ref.paragraphs[i]._p) for i in (7, 8, 9)]
    width = len(ref.paragraphs[7].text or "") or 115
    return paras, width


def _two_column_signature_line(left: str, right: str, width: int) -> str:
    """Pad left/right columns to match the printed protocol signature block."""
    pad = max(2, width - len(left) - len(right))
    return f"{left}{' ' * pad}{right}"


def _last_worksheet_body_element(doc: Document):
    """Return the body element for the last worksheet / appearance table."""
    last = None
    for child in doc.element.body:
        if not child.tag.endswith("tbl"):
            continue
        table = Table(child, doc)
        if _is_worksheet_table(table) or _is_appearance_only_table(table):
            last = child
    return last


def _clear_paragraph_tabs(paragraph: Paragraph) -> None:
    """Remove tab stops (dot leaders) from cloned signature paragraphs."""
    p_pr = paragraph._element.get_or_add_pPr()
    tabs = p_pr.find(qn("w:tabs"))
    if tabs is not None:
        p_pr.remove(tabs)


def _insert_blank_paragraph_after(doc: Document, after_el) -> Paragraph:
    """Insert an empty body paragraph after *after_el*."""
    new_p = OxmlElement("w:p")
    after_el.addnext(new_p)
    return Paragraph(new_p, doc)


def _insert_signature_paragraphs_after(
    doc: Document,
    after_el,
    para_xml_list: list[Any],
    texts: list[str],
) -> list[Paragraph]:
    """Insert cloned signature paragraphs after *after_el* and set line text."""
    inserted: list[Paragraph] = []
    current = after_el
    for para_xml, line_text in zip(para_xml_list, texts):
        new_el = deepcopy(para_xml)
        current.addnext(new_el)
        para = Paragraph(new_el, doc)
        _clear_paragraph_numbering(para)
        _clear_paragraph_tabs(para)
        _set_paragraph_text(para, line_text)
        inserted.append(para)
        current = new_el
    return inserted


def _clear_paragraph_keep_with_next(paragraph: Paragraph) -> None:
    p_pr = paragraph._element.get_or_add_pPr()
    keep = p_pr.find(qn("w:keepNext"))
    if keep is not None:
        p_pr.remove(keep)


def _keep_signature_lines_together(sig_paras: list[Paragraph]) -> None:
    """Chain signature lines only — do not glue them to the last worksheet."""
    if not sig_paras:
        return
    for para in sig_paras[:-1]:
        _set_paragraph_keep_with_next(para)
    _clear_paragraph_keep_with_next(sig_paras[-1])


def _apply_protocol_end_signatures(
    doc: Document,
    sample: SampleRecord,
    header: ProtocolHeader,
) -> None:
    """
    End-of-protocol analyst / checker block matching the printed protocol sheet.

    Two blank lines after the last worksheet, then three wide left/right lines.
    """
    _remove_body_signature_blocks(doc)

    para_xml, width = _signature_reference_layout()
    if not para_xml:
        return

    analyst = _protocol_issued_to(sample, header)
    date_str = _analysis_date_display(header)

    lines = [
        _two_column_signature_line("Analysed By:", "Checked By:", width),
        _two_column_signature_line(analyst or "Name", "Technical Manager:", width),
        _two_column_signature_line(
            date_str or "Dated signature:",
            "Dated Signature:",
            width,
        ),
    ]

    anchor = _last_worksheet_body_element(doc)
    if anchor is None:
        anchor = doc.element.body[-1] if len(doc.element.body) else None
    if anchor is None:
        return

    insert_after = anchor
    next_el = insert_after.getnext()
    while next_el is not None and next_el.tag.endswith("p"):
        para = Paragraph(next_el, doc)
        if (para.text or "").strip() or _paragraph_has_page_break(next_el):
            break
        to_remove = next_el
        next_el = next_el.getnext()
        parent = to_remove.getparent()
        if parent is not None:
            parent.remove(to_remove)

    for _ in range(2):
        insert_after = _insert_blank_paragraph_after(doc, insert_after)._element

    sig_paras = _insert_signature_paragraphs_after(doc, insert_after, para_xml, lines)
    _keep_signature_lines_together(sig_paras)


def _consolidate_to_single_section(doc: Document) -> None:
    """Merge multi-section documents (Jaggery) into one continuous section."""
    body = doc.element.body
    for child in body:
        if not child.tag.endswith("p"):
            continue
        p_pr = child.find(qn("w:pPr"))
        if p_pr is None:
            continue
        sect_pr = p_pr.find(qn("w:sectPr"))
        if sect_pr is not None:
            p_pr.remove(sect_pr)


SUMMARY_HEADER_LABELS = ("Sr No.", "Parameter", "Method", "Result", "Unit")
OBSERVATION_TABLE_HEADING = "OBSERVATION TABLE :"


def _is_summary_table(table) -> bool:
    if not table.rows:
        return False
    hdr = " ".join((c.text or "").strip() for c in table.rows[0].cells).lower()
    has_sr = "sr" in hdr
    has_result = "result" in hdr
    has_name_col = any(
        token in hdr for token in ("parameter", "name of test")
    )
    has_method = "method" in hdr
    return has_sr and has_result and (has_name_col or has_method)


def _find_summary_table(doc: Document):
    for table in doc.tables:
        if _is_summary_table(table):
            return table
    return None


def _is_observation_heading(text: str) -> bool:
    return "observation table" in (text or "").strip().lower()


def _is_appearance_only_table(table) -> bool:
    if len(table.rows) != 1 or len(table.rows[0].cells) != 1:
        return False
    return "appearance" in (table.rows[0].cells[0].text or "").lower()


def _is_worksheet_section_start(doc: Document, element) -> bool:
    tag = element.tag.split("}")[-1]
    if tag == "p":
        text = (Paragraph(element, doc).text or "").strip()
        if not text or text == "Result Table:":
            return False
        if _is_observation_heading(text):
            return True
        first_line = text.split("\n", 1)[0].strip()
        return first_line.endswith(":")
    if tag == "tbl":
        table = Table(element, doc)
        if _is_worksheet_table(table) or _is_appearance_only_table(table):
            return True
    return False


def _insert_page_break_before(element) -> None:
    page_break_p = OxmlElement("w:p")
    run = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run.append(br)
    page_break_p.append(run)
    element.addprevious(page_break_p)


def _insert_paragraph_before(doc: Document, before_el, text: str) -> Paragraph:
    new_p = OxmlElement("w:p")
    run = OxmlElement("w:r")
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    new_p.append(run)
    before_el.addprevious(new_p)
    return Paragraph(new_p, doc)


def _ensure_observation_section_starts_page_2(doc: Document) -> None:
    """Keep page 1 for the result summary; start worksheets on page 2."""
    summary = _find_summary_table(doc)
    if summary is None:
        return

    body = doc.element.body
    siblings = list(body)
    try:
        start_idx = siblings.index(summary._tbl) + 1
    except ValueError:
        return

    observation_el = None
    worksheet_el = None
    for child in siblings[start_idx:]:
        if child.tag.endswith("p"):
            text = (Paragraph(child, doc).text or "").strip()
            if not text:
                continue
            if _is_observation_heading(text):
                observation_el = child
                break
            if worksheet_el is None and _is_worksheet_section_start(doc, child):
                worksheet_el = child
        elif child.tag.endswith("tbl") and worksheet_el is None:
            if _is_worksheet_section_start(doc, child):
                worksheet_el = child

    if observation_el is None and worksheet_el is None:
        return

    if observation_el is None:
        assert worksheet_el is not None
        observation_el = _insert_paragraph_before(
            doc, worksheet_el, OBSERVATION_TABLE_HEADING
        )._element
    else:
        para = Paragraph(observation_el, doc)
        if (para.text or "").strip() != OBSERVATION_TABLE_HEADING:
            _set_paragraph_text(para, OBSERVATION_TABLE_HEADING)

    if observation_el.getprevious() is None or not _paragraph_has_page_break(
        observation_el.getprevious()
    ):
        _insert_page_break_before(observation_el)


def _paragraph_has_page_break(paragraph_el) -> bool:
    if paragraph_el is None or not paragraph_el.tag.endswith("p"):
        return False
    for br in paragraph_el.findall(".//" + qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False


def _apply_reference_page_margins(doc: Document) -> None:
    """Normalize section margins to match the protocol header/footer reference."""
    ref_path = _protocol_layout_reference_path()
    if not ref_path.exists():
        return
    ref_sec = Document(str(ref_path)).sections[0]
    for section in doc.sections:
        section.left_margin = ref_sec.left_margin
        section.right_margin = ref_sec.right_margin
        section.top_margin = ref_sec.top_margin
        section.bottom_margin = ref_sec.bottom_margin
        section.header_distance = ref_sec.header_distance
        section.footer_distance = ref_sec.footer_distance


def _table_grid_col_twips(table) -> list[int]:
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is None:
        return []
    return [int(col.get(qn("w:w"))) for col in grid.findall(qn("w:gridCol"))]


def _table_grid_width_inches(table) -> float:
    twips = _table_grid_col_twips(table)
    return sum(twips) / 1440 if twips else 0.0


def _usable_page_width_inches(section) -> float:
    return section.page_width.inches - section.left_margin.inches - section.right_margin.inches


def _nutrition_reference_tables() -> tuple[Document, Any, Any, Any, Any | None]:
    """Load Basic Nutrition template tables used for width normalization."""
    ref = Document(str(NUTRITION_TEMPLATE_PATH))
    header_ref = None
    if ref.sections[0].header.tables:
        header_ref = ref.sections[0].header.tables[0]
    return ref, ref.tables[0], ref.tables[1], ref.tables[3], header_ref


def _replace_table_grid_from_reference(table, ref_table) -> None:
    """Replace w:tblGrid (and tblW) so Word/PDF use reference column widths."""
    ref_grid = ref_table._tbl.find(qn("w:tblGrid"))
    if ref_grid is None:
        return
    ref_cols = [int(c.get(qn("w:w"))) for c in ref_grid.findall(qn("w:gridCol"))]
    if not ref_cols:
        return
    ncol = len(table.columns)
    if ncol != len(ref_cols):
        return

    tbl = table._tbl
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)

    new_grid = deepcopy(ref_grid)
    tbl_pr = tbl.tblPr
    if tbl_pr is not None:
        tbl_pr.addnext(new_grid)
    else:
        tbl.insert(0, new_grid)

    ref_tbl_pr = ref_table._tbl.tblPr
    if ref_tbl_pr is not None:
        ref_tbl_w = ref_tbl_pr.find(qn("w:tblW"))
        if ref_tbl_w is not None:
            doc_tbl_pr = tbl.tblPr
            if doc_tbl_pr is None:
                doc_tbl_pr = OxmlElement("w:tblPr")
                tbl.insert(0, doc_tbl_pr)
            old_tbl_w = doc_tbl_pr.find(qn("w:tblW"))
            if old_tbl_w is not None:
                doc_tbl_pr.remove(old_tbl_w)
            doc_tbl_pr.append(deepcopy(ref_tbl_w))

    for row in table.rows:
        for col_idx, cell in enumerate(row.cells):
            if col_idx >= len(ref_cols):
                break
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(ref_cols[col_idx]))
            tc_w.set(qn("w:type"), "dxa")


def _ensure_table_tbl_pr(table):
    tbl = table._tbl
    doc_tbl_pr = tbl.tblPr
    if doc_tbl_pr is None:
        doc_tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, doc_tbl_pr)
    return doc_tbl_pr


def _set_table_tbl_w(table, width_twips: int) -> None:
    """Set w:tblW so Word/PDF use the same outer width as tblGrid."""
    doc_tbl_pr = _ensure_table_tbl_pr(table)
    old_tbl_w = doc_tbl_pr.find(qn("w:tblW"))
    if old_tbl_w is not None:
        doc_tbl_pr.remove(old_tbl_w)
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:w"), str(width_twips))
    tbl_w.set(qn("w:type"), "dxa")
    doc_tbl_pr.append(tbl_w)


def _table_tbl_ind_twips(table) -> int | None:
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        return None
    ind = tbl_pr.find(qn("w:tblInd"))
    if ind is None or ind.get(qn("w:type")) != "dxa":
        return None
    return int(ind.get(qn("w:w")))


def _set_table_tbl_ind(table, ind_twips: int) -> None:
    doc_tbl_pr = _ensure_table_tbl_pr(table)
    old_ind = doc_tbl_pr.find(qn("w:tblInd"))
    if old_ind is not None:
        doc_tbl_pr.remove(old_ind)
    tbl_ind = OxmlElement("w:tblInd")
    tbl_ind.set(qn("w:w"), str(ind_twips))
    tbl_ind.set(qn("w:type"), "dxa")
    doc_tbl_pr.append(tbl_ind)


def _scale_table_grid_to_width(table, target_twips: int) -> None:
    """Proportionally scale tblGrid/tcW so column sum equals target_twips."""
    cols = _table_grid_col_twips(table)
    if not cols or target_twips <= 0:
        return
    if len(cols) == 1:
        _set_table_single_column_width(table, target_twips)
        return

    current = sum(cols)
    if current <= 0:
        return

    scaled: list[int] = []
    remaining = target_twips
    for idx, width in enumerate(cols):
        if idx == len(cols) - 1:
            scaled.append(max(1, remaining))
            continue
        new_width = max(1, round(width * target_twips / current))
        scaled.append(new_width)
        remaining -= new_width

    drift = target_twips - sum(scaled)
    if drift:
        scaled[-1] = max(1, scaled[-1] + drift)

    tbl = table._tbl
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    new_grid = OxmlElement("w:tblGrid")
    for width in scaled:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        new_grid.append(col)
    tbl_pr = tbl.tblPr
    if tbl_pr is not None:
        tbl_pr.addnext(new_grid)
    else:
        tbl.insert(0, new_grid)

    for row in table.rows:
        for col_idx, cell in enumerate(row.cells):
            if col_idx >= len(scaled):
                break
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(scaled[col_idx]))
            tc_w.set(qn("w:type"), "dxa")

    _set_table_tbl_w(table, target_twips)


def _set_table_single_column_width(table, width_twips: int) -> None:
    """Replace tblGrid with one column of ``width_twips`` (full sample-table width)."""
    tbl = table._tbl
    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    new_grid = OxmlElement("w:tblGrid")
    col = OxmlElement("w:gridCol")
    col.set(qn("w:w"), str(width_twips))
    new_grid.append(col)
    tbl_pr = tbl.tblPr
    if tbl_pr is not None:
        tbl_pr.addnext(new_grid)
    else:
        tbl.insert(0, new_grid)
    for row in table.rows:
        if not row.cells:
            continue
        tc_pr = row.cells[0]._tc.get_or_add_tcPr()
        tc_w = tc_pr.find(qn("w:tcW"))
        if tc_w is None:
            tc_w = OxmlElement("w:tcW")
            tc_pr.append(tc_w)
        tc_w.set(qn("w:w"), str(width_twips))
        tc_w.set(qn("w:type"), "dxa")
    _set_table_tbl_w(table, width_twips)


def _worksheet_third_column_header(table) -> str:
    """Return Unit or Readings for the third worksheet header cell."""
    if len(table.rows) < 2 or len(table.rows[0].cells) < 3:
        return "Readings"
    hdr_third = (table.rows[0].cells[2].text or "").strip().lower()
    if hdr_third == "unit":
        return "Unit"
    for row in table.rows[1:4]:
        if len(row.cells) < 3:
            continue
        c1 = (row.cells[1].text or "").strip().lower()
        c2 = (row.cells[2].text or "").strip().lower()
        if c2 in BARE_UNIT_PLACEHOLDERS and not c1.endswith(c2):
            return "Unit"
    return "Readings"


def _normalize_food_worksheet_headers(doc: Document, sample: SampleRecord) -> None:
    """Label worksheet header rows (Description | Readings | Readings/Unit)."""
    if normalize_category(sample.category) == CATEGORY_WATER:
        return
    for table in doc.tables:
        if not _is_worksheet_table(table):
            continue
        if _is_result_only_worksheet_table(table):
            continue
        if len(table.rows) < 1:
            continue
        hdr0 = (table.rows[0].cells[0].text or "").strip().lower()
        cells = table.rows[0].cells
        if "description" in hdr0 and len(cells) >= 3:
            _set_cell(cells[0], "Description")
            _set_cell(cells[1], "Readings")
            _set_cell(cells[2], _worksheet_third_column_header(table))
        elif ("sr. no" in hdr0 or "sr no" in hdr0) and len(cells) >= 3:
            _set_cell(cells[0], "Sr. No.")
            _set_cell(cells[1], "Parameter")
            _set_cell(cells[2], "Reading")


def _normalize_food_protocol_table_widths(doc: Document) -> None:
    """
    Fit food-protocol tables to Basic Nutrition reference widths so PDF does not
    clip the Unit column after 1\" margins are applied.
    """
    if not NUTRITION_TEMPLATE_PATH.exists():
        return
    _, sample_ref, summary_ref, worksheet_ref, header_ref = _nutrition_reference_tables()
    sample_width = sum(_table_grid_col_twips(sample_ref))

    for table in doc.tables:
        if _is_appearance_only_table(table):
            if sample_width:
                _set_table_single_column_width(table, sample_width)
        elif _is_sample_info_table(table):
            _replace_table_grid_from_reference(table, sample_ref)
        elif _is_summary_table(table):
            _replace_table_grid_from_reference(table, summary_ref)
        elif _is_worksheet_table(table):
            if len(table.columns) == len(worksheet_ref.columns):
                _replace_table_grid_from_reference(table, worksheet_ref)

    if header_ref is not None:
        for section in doc.sections:
            for table in section.header.tables:
                if table.rows and len(table.rows[0].cells) >= 6:
                    _replace_table_grid_from_reference(table, header_ref)


def _is_food_protocol_outer_box_table(table) -> bool:
    return (
        _is_appearance_only_table(table)
        or _is_sample_info_table(table)
        or _is_summary_table(table)
        or _is_worksheet_table(table)
    )


def _canonical_food_protocol_outer_frame() -> tuple[int, int]:
    """Return worksheet-reference outer width and left indent (twips)."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return 9990, -162
    _, _, _, worksheet_ref, _ = _nutrition_reference_tables()
    target_width = sum(_table_grid_col_twips(worksheet_ref)) or 9990
    target_ind = _table_tbl_ind_twips(worksheet_ref)
    if target_ind is None:
        target_ind = -162
    return target_width, target_ind


def _apply_food_protocol_outer_frame(
    table,
    target_width: int,
    target_ind: int,
) -> None:
    _scale_table_grid_to_width(table, target_width)
    _set_table_tbl_ind(table, target_ind)
    _make_table_inline(table)


def _unify_food_protocol_outer_boxes(doc: Document) -> None:
    """Force food-protocol tables to share one left edge and outer width."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return
    target_width, target_ind = _canonical_food_protocol_outer_frame()

    for table in doc.tables:
        if _is_food_protocol_outer_box_table(table):
            _apply_food_protocol_outer_frame(table, target_width, target_ind)

    for section in doc.sections:
        for table in section.header.tables:
            if table.rows and len(table.rows[0].cells) >= 6:
                _apply_food_protocol_outer_frame(table, target_width, target_ind)
        for table in section.footer.tables:
            _apply_food_protocol_outer_frame(table, target_width, target_ind)


def _normalize_food_protocol_footer_layout(doc: Document) -> None:
    """Align footer approval table to Basic Nutrition reference grid and indent."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return
    ref = Document(str(NUTRITION_TEMPLATE_PATH))
    if not ref.sections[0].footer.tables:
        return
    footer_ref = ref.sections[0].footer.tables[0]
    for section in doc.sections:
        for table in section.footer.tables:
            if len(table.columns) == len(footer_ref.columns):
                _replace_table_grid_from_reference(table, footer_ref)
            _copy_table_layout_from_reference(table, footer_ref)
    _unify_food_protocol_outer_boxes(doc)


def _copy_table_layout_from_reference(table, ref_table) -> None:
    """Copy tblInd from Basic Nutrition reference; keep tables inline for PDF export."""
    ref_tbl_pr = ref_table._tbl.tblPr
    tbl = table._tbl
    doc_tbl_pr = tbl.tblPr
    if doc_tbl_pr is None:
        doc_tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, doc_tbl_pr)

    old_ind = doc_tbl_pr.find(qn("w:tblInd"))
    if old_ind is not None:
        doc_tbl_pr.remove(old_ind)

    if ref_tbl_pr is not None:
        ref_ind = ref_tbl_pr.find(qn("w:tblInd"))
        if ref_ind is not None:
            doc_tbl_pr.append(deepcopy(ref_ind))

    _make_table_inline(table)


def _normalize_food_protocol_table_alignment(doc: Document) -> None:
    """Align food-protocol table left edges to Basic Nutrition reference."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return
    _, sample_ref, summary_ref, worksheet_ref, header_ref = _nutrition_reference_tables()

    for table in doc.tables:
        if _is_appearance_only_table(table):
            _copy_table_layout_from_reference(table, sample_ref)
        elif _is_sample_info_table(table):
            _copy_table_layout_from_reference(table, sample_ref)
        elif _is_summary_table(table):
            _copy_table_layout_from_reference(table, summary_ref)
        elif _is_worksheet_table(table):
            _copy_table_layout_from_reference(table, worksheet_ref)

    if header_ref is not None:
        for section in doc.sections:
            for table in section.header.tables:
                if table.rows and len(table.rows[0].cells) >= 6:
                    _copy_table_layout_from_reference(table, header_ref)


def _paragraph_is_empty(paragraph: Paragraph) -> bool:
    return not (paragraph.text or "").strip()


def _clear_paragraph_spacing(paragraph: Paragraph) -> None:
    p_pr = paragraph._element.get_or_add_pPr()
    spacing = p_pr.find(qn("w:spacing"))
    if spacing is not None:
        p_pr.remove(spacing)


def _strip_leading_body_spacers(doc: Document) -> None:
    """Drop empty leading body paragraphs left by the Jaggery template."""
    body = doc.element.body
    for child in list(body):
        if child.tag.endswith("tbl"):
            break
        if not child.tag.endswith("p"):
            break
        para = Paragraph(child, doc)
        if _paragraph_is_empty(para):
            _delete_paragraph(para)
        else:
            break


def _strip_paragraphs_between_summary_and_observation(doc: Document) -> None:
    """Remove Jaggery spacer paragraphs between the summary table and page 2."""
    summary = _find_summary_table(doc)
    if summary is None:
        return

    next_el = summary._tbl.getnext()
    while next_el is not None:
        if next_el.tag.endswith("p"):
            para = Paragraph(next_el, doc)
            text = (para.text or "").strip()
            if _is_observation_heading(text):
                break
            if text == "Result Table:":
                next_el = next_el.getnext()
                continue
            if not text:
                if _paragraph_has_page_break(next_el):
                    _clear_paragraph_spacing(para)
                    next_el = next_el.getnext()
                    continue
                to_remove = next_el
                next_el = next_el.getnext()
                parent = to_remove.getparent()
                if parent is not None:
                    parent.remove(to_remove)
                continue
            break
        if next_el.tag.endswith("tbl"):
            break
        next_el = next_el.getnext()


def _strip_empty_paragraphs_before_table(doc: Document, table) -> None:
    """Collapse blank spacer paragraphs immediately above a table."""
    prev = table._tbl.getprevious()
    while prev is not None:
        if prev.tag.endswith("tbl"):
            break
        if not prev.tag.endswith("p"):
            break
        para = Paragraph(prev, doc)
        if not _paragraph_is_empty(para):
            break
        to_remove = prev
        prev = prev.getprevious()
        parent = to_remove.getparent()
        if parent is not None:
            parent.remove(to_remove)


def _strip_worksheet_title_spacers(doc: Document) -> None:
    """Remove empty spacer paragraphs between section titles and worksheet tables."""
    seen_observation = False
    for child in doc.element.body:
        if child.tag.endswith("p"):
            text = (Paragraph(child, doc).text or "").strip()
            if _is_observation_heading(text):
                seen_observation = True
        elif child.tag.endswith("tbl") and seen_observation:
            table = Table(child, doc)
            if _is_worksheet_table(table):
                _strip_empty_paragraphs_before_table(doc, table)


def _tighten_food_protocol_page1_spacing(doc: Document) -> None:
    """Reduce leftover vertical spacing on page-1 labels and tables."""
    summary = _find_summary_table(doc)
    for paragraph in doc.paragraphs:
        text = (paragraph.text or "").strip()
        if text == "Result Table:":
            _clear_paragraph_spacing(paragraph)
    if summary is not None:
        prev = summary._tbl.getprevious()
        if prev is not None and prev.tag.endswith("p"):
            para = Paragraph(prev, doc)
            if (para.text or "").strip() == "Result Table:":
                _clear_paragraph_spacing(para)


def _normalize_food_protocol_visual_layout(doc: Document) -> None:
    """Align tables and remove spacer paragraphs for Nutrition house style."""
    _normalize_food_protocol_table_alignment(doc)
    _strip_leading_body_spacers(doc)
    _tighten_food_protocol_page1_spacing(doc)
    _strip_paragraphs_between_summary_and_observation(doc)
    _strip_worksheet_title_spacers(doc)


def _normalize_jaggery_summary_headers(doc: Document, sample: SampleRecord) -> None:
    if normalize_category(sample.category) == CATEGORY_WATER or _is_nutrition_sample(
        sample
    ):
        return
    table = _find_summary_table(doc)
    if table is None or not table.rows:
        return
    cells = table.rows[0].cells
    for idx, label in enumerate(SUMMARY_HEADER_LABELS):
        if idx < len(cells):
            _set_cell(cells[idx], label)


BARE_UNIT_PLACEHOLDERS = frozenset(
    {"g", "ml", "%", "ppm", "—", "-", "ntu", "μs/cm", "us/cm"}
)
SECTION_TITLE_NUM_RE = re.compile(r"^\d+\.\s*")


def _nutrition_page1_header_table_xml():
    """Clone the Basic Nutrition body header table (2 rows before identity insert)."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return None
    ref = Document(str(NUTRITION_TEMPLATE_PATH))
    if not ref.tables:
        return None
    return deepcopy(ref.tables[0]._tbl)


def _nutrition_repeating_header_table_xml():
    """Clone the nutrition section-header identity table (Protocol No row)."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return None
    ref = Document(str(NUTRITION_TEMPLATE_PATH))
    if not ref.sections[0].header.tables:
        return None
    return deepcopy(ref.sections[0].header.tables[0]._tbl)


def _remap_embedded_images(
    source_part,
    target_part,
    element,
    r_id_map: dict[str, str] | None = None,
) -> None:
    """Copy inline header/footer images when cloning XML into another document."""
    if r_id_map is None:
        r_id_map = {}
    embed_attr = qn("r:embed")
    for blip in element.iter():
        if blip.tag != qn("a:blip"):
            continue
        old_r_id = blip.get(embed_attr)
        if not old_r_id:
            continue
        if old_r_id in r_id_map:
            blip.set(embed_attr, r_id_map[old_r_id])
            continue
        try:
            source_image = source_part.related_parts[old_r_id]
        except KeyError:
            continue
        new_r_id = target_part.relate_to(source_image, source_image.content_type)
        r_id_map[old_r_id] = new_r_id
        blip.set(embed_attr, new_r_id)


def _fill_letterhead_pages_count(header) -> None:
    """Replace static Pages value with a Word NUMPAGES field (total page count)."""
    from services.docx_layout import _append_field_run

    for table in header.tables:
        for row in table.rows:
            cells = row.cells
            for idx, cell in enumerate(cells):
                label = (cell.text or "").strip().lower()
                if not label.startswith("pages"):
                    continue
                value_cell = cells[idx + 1] if idx + 1 < len(cells) else cell
                para = value_cell.paragraphs[0] if value_cell.paragraphs else value_cell.add_paragraph()
                _set_paragraph_text(para, "")
                _append_field_run(para, " NUMPAGES ", placeholder="1")
                return


def _apply_letterhead_logo_blob(header) -> None:
    """Swap header image bytes for the circular Surendra Laboratories logo."""
    if not PROTOCOL_LETTERHEAD_LOGO_PATH.exists():
        return
    blob = PROTOCOL_LETTERHEAD_LOGO_PATH.read_bytes()
    for rel in header.part.rels.values():
        if "image" in rel.reltype:
            rel.target_part._blob = blob


def _copy_protocol_letterhead_header(doc: Document) -> bool:
    """Clone letterhead header from reference/protocol.docx with logo images intact."""
    if not PROTOCOL_HEADER_FOOTER_PATH.exists():
        return False
    ref_doc = Document(str(PROTOCOL_HEADER_FOOTER_PATH))
    ref_header = ref_doc.sections[0].header
    ref_part = ref_header.part

    for section in doc.sections:
        header = section.header
        header.is_linked_to_previous = False
        hdr_el = header._element
        for child in list(hdr_el):
            hdr_el.remove(child)
        r_id_map: dict[str, str] = {}
        for child in ref_header._element:
            new_child = deepcopy(child)
            _remap_embedded_images(ref_part, header.part, new_child, r_id_map)
            hdr_el.append(new_child)
        _apply_letterhead_logo_blob(header)
        _fill_letterhead_pages_count(header)
    return True


def _protocol_letterhead_header_children_xml() -> list[Any]:
    """Legacy helper — prefer _copy_protocol_letterhead_header()."""
    if not PROTOCOL_HEADER_FOOTER_PATH.exists():
        return []
    ref_hdr = Document(str(PROTOCOL_HEADER_FOOTER_PATH)).sections[0].header._element
    return [deepcopy(child) for child in ref_hdr]


def _fill_protocol_letterhead_header(header, proto_header: ProtocolHeader) -> None:
    """Fill dynamic letterhead fields (page count only; no protocol number in header)."""
    del proto_header
    _fill_letterhead_pages_count(header)


def _is_legacy_page1_header_table(table) -> bool:
    if not table.rows or _is_summary_table(table):
        return False
    if _is_repeat_protocol_header_table(table):
        return True
    first = (table.rows[0].cells[0].text or "").strip().lower()
    return first.startswith("protocol no") or first.startswith("sample name")


def _is_sample_info_table(table) -> bool:
    if not table.rows or _is_summary_table(table):
        return False
    first = (table.rows[0].cells[0].text or "").strip().lower()
    return first.startswith("sample name")


def _fill_reference_sample_info_table(
    table,
    sample: SampleRecord,
    header: ProtocolHeader,
) -> None:
    """Fill the 2-row sample table matching Basic Nutrition reference page 1."""
    if len(table.rows) >= 2 and len(table.rows[0].cells) >= 4:
        _set_cell(table.rows[0].cells[0], "Sample Name")
        _set_cell(table.rows[0].cells[1], sample.sample_name or "")
        _set_cell(table.rows[0].cells[2], "Sample Received on")
        _set_cell(table.rows[0].cells[3], _fmt_date(header.sample_received_on))
        _set_cell(table.rows[1].cells[0], "Lab Code")
        _set_cell(
            table.rows[1].cells[1],
            sample.lab_code or sample.sample_code or "",
        )
        _set_cell(table.rows[1].cells[2], "Date of Analysis")
        _set_cell(table.rows[1].cells[3], _analysis_date_display(header))


def _remove_body_tables_before_summary(doc: Document) -> None:
    summary = _find_summary_table(doc)
    if summary is None:
        return
    body = doc.element.body
    for child in list(body):
        if child is summary._tbl:
            break
        if child.tag.endswith("tbl"):
            body.remove(child)


def _replace_page1_body_with_reference_layout(
    doc: Document,
    sample: SampleRecord,
    header: ProtocolHeader,
) -> None:
    """
    Match Basic Nutrition reference page-1 body:

    Sample-info table (2 rows) -> Result Table: -> summary table.
    Protocol No / issued-to / issued-by live in the section header only.
    """
    summary = _find_summary_table(doc)
    if summary is None:
        return
    _remove_body_tables_before_summary(doc)

    tbl_xml = _nutrition_page1_header_table_xml()
    if tbl_xml is None:
        return

    insert_before = summary._tbl
    prev = summary._tbl.getprevious()
    while prev is not None:
        if prev.tag.endswith("p"):
            para = Paragraph(prev, doc)
            if (para.text or "").strip() == "Result Table:":
                insert_before = prev
                break
        if prev.tag.endswith("tbl"):
            break
        prev = prev.getprevious()

    insert_before.addprevious(deepcopy(tbl_xml))
    for table in doc.tables:
        if table is summary:
            break
        if _is_sample_info_table(table):
            _fill_reference_sample_info_table(table, sample, header)
            _make_table_inline(table)
            for row in table.rows:
                _set_row_cant_split(row)
            break


def _nutrition_header_trailing_paragraphs_xml() -> list[Any]:
    """Clone blank header paragraphs after the Protocol No table in the nutrition ref."""
    if not NUTRITION_TEMPLATE_PATH.exists():
        return []
    ref_hdr = Document(str(NUTRITION_TEMPLATE_PATH)).sections[0].header._element
    trailing: list[Any] = []
    seen_table = False
    for child in ref_hdr:
        if child.tag.endswith("tbl"):
            seen_table = True
            trailing.clear()
            continue
        if seen_table and child.tag.endswith("p"):
            trailing.append(deepcopy(child))
    return trailing


def _normalize_food_protocol_section_header_spacing(doc: Document) -> None:
    """Match Basic Nutrition gap: Protocol No table first, then trailing blank lines."""
    trailing_paras = _nutrition_header_trailing_paragraphs_xml()
    if not trailing_paras:
        return

    for section in doc.sections:
        hdr_el = section.header._element
        protocol_tbl = None
        for table in section.header.tables:
            if table.rows and len(table.rows[0].cells) >= 6:
                protocol_tbl = table._tbl
                break
        if protocol_tbl is None:
            continue

        for child in list(hdr_el):
            if child is protocol_tbl:
                continue
            hdr_el.remove(child)

        for para_xml in trailing_paras:
            hdr_el.append(deepcopy(para_xml))


def _apply_repeating_protocol_header(doc: Document, header: ProtocolHeader) -> bool:
    """
    Apply section header from protocol.docx letterhead or nutrition identity row.

    Returns True when the protocol.docx letterhead (logo + NUMPAGES) was applied.
    """
    if _copy_protocol_letterhead_header(doc):
        return True

    tbl_xml = _nutrition_repeating_header_table_xml()
    if tbl_xml is None:
        return False
    for section in doc.sections:
        hdr = section.header
        for table in list(hdr.tables):
            parent = table._tbl.getparent()
            if parent is not None:
                parent.remove(table._tbl)
        hdr._element.append(deepcopy(tbl_xml))
        table = hdr.tables[-1]
        if table.rows and len(table.rows[0].cells) >= 6:
            cells = table.rows[0].cells
            _set_cell(cells[1], header.protocol_no or "")
            _set_cell(cells[3], header.issued_to or "")
            _set_cell(cells[5], header.issued_by or "")
    return False


def _appearance_result_text(
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> str:
    if "appearance" in by_key:
        text = (by_key["appearance"].result_value or "").strip()
        if text:
            return text
    return (header.appearance_text or "").strip()


def _fill_appearance_worksheet_block(
    doc: Document,
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> None:
    """Show saved appearance text in the observation-section appearance block."""
    text = _appearance_result_text(header, by_key)
    if not text:
        return
    for table in doc.tables:
        if not _is_appearance_only_table(table):
            continue
        cell = table.rows[0].cells[0]
        for paragraph in cell.paragraphs:
            _clear_paragraph_numbering(paragraph)
        _set_cell(cell, f"APPEARANCE: {text}")
        return


def _promote_appearance_table_to_paragraph(doc: Document) -> None:
    """Replace the 1x1 appearance table with a body paragraph for stable PDF flow."""
    for table in list(doc.tables):
        if not _is_appearance_only_table(table):
            continue
        text = (table.rows[0].cells[0].text or "").strip()
        if not text:
            _delete_table(table)
            return
        new_p = OxmlElement("w:p")
        run = OxmlElement("w:r")
        text_el = OxmlElement("w:t")
        text_el.set(qn("xml:space"), "preserve")
        text_el.text = text
        run.append(text_el)
        new_p.append(run)
        table._tbl.addprevious(new_p)
        _delete_table(table)
        return


def _keep_page1_block_together(doc: Document) -> None:
    """Keep sample table + Result Table + summary on page 1 together."""
    summary = _find_summary_table(doc)
    if summary is not None:
        for row in summary.rows:
            _set_row_cant_split(row)
    for table in doc.tables:
        if _is_sample_info_table(table):
            for row in table.rows:
                _set_row_cant_split(row)
            break
    for paragraph in doc.paragraphs:
        if (paragraph.text or "").strip() == "Result Table:":
            _set_paragraph_keep_with_next(paragraph)
            break


def _is_bare_unit_placeholder(text: str) -> bool:
    stripped = (text or "").strip().lower()
    return stripped in BARE_UNIT_PLACEHOLDERS


def _row_has_reading_value(row) -> bool:
    if len(row.cells) < 2:
        return False
    for cell in row.cells[1:]:
        text = (cell.text or "").strip()
        if not text or _is_bare_unit_placeholder(text):
            continue
        return True
    return False


def _clean_bare_unit_placeholders(doc: Document) -> None:
    """Remove lone g/ml/% cells when the row has no saved reading."""
    for table in doc.tables:
        if not _is_worksheet_table(table):
            continue
        for row in table.rows[1:]:
            if _row_has_reading_value(row):
                continue
            for idx, cell in enumerate(row.cells):
                if idx == 0:
                    continue
                if _is_bare_unit_placeholder(cell.text):
                    _set_cell(cell, "")


def _clear_paragraph_numbering(paragraph) -> None:
    """Remove auto-list numbering so manual section numbers do not double up."""
    p_pr = paragraph._element.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is not None:
        p_pr.remove(num_pr)
    p_style = p_pr.find(qn("w:pStyle"))
    if p_style is not None:
        p_pr.remove(p_style)


def _strip_section_title_number(text: str) -> str:
    first_line = (text or "").split("\n", 1)[0].strip()
    while True:
        stripped = SECTION_TITLE_NUM_RE.sub("", first_line, count=1).strip()
        if stripped == first_line:
            break
        first_line = stripped
    return first_line


def _renumber_worksheet_section_titles(doc: Document, conducted: set[str]) -> None:
    """Number worksheet section titles 1, 2, 3... in document order."""
    del conducted  # order follows surviving blocks after prune
    seen_observation = False
    section_idx = 0
    for child in doc.element.body:
        if child.tag.endswith("p"):
            para = Paragraph(child, doc)
            text = (para.text or "").strip()
            if not text:
                continue
            if _is_observation_heading(text):
                seen_observation = True
                continue
            if not seen_observation or text == "Result Table:":
                continue
            if _is_body_signature_paragraph(text):
                continue
            first_line = text.split("\n", 1)[0].strip()
            if not first_line.endswith(":"):
                continue
            section_idx += 1
            base = _strip_section_title_number(first_line)
            lines = text.split("\n")
            new_first = f"{section_idx}. {base}"
            new_text = "\n".join([new_first] + lines[1:]) if len(lines) > 1 else new_first
            _clear_paragraph_numbering(para)
            _set_paragraph_text(para, new_text)
        elif child.tag.endswith("tbl") and seen_observation:
            table = Table(child, doc)
            if not _is_appearance_only_table(table):
                continue
            section_idx += 1
            cell = table.rows[0].cells[0]
            raw = (cell.text or "").strip()
            lines = raw.split("\n")
            title = _strip_section_title_number(lines[0])
            rest = "\n".join(lines[1:]).strip()
            new_text = f"{section_idx}. {title}"
            if rest:
                new_text = f"{new_text}\n{rest}"
            for paragraph in cell.paragraphs:
                _clear_paragraph_numbering(paragraph)
            _set_cell(cell, new_text)


def _paragraph_is_page_break_only(paragraph_el) -> bool:
    """True when a paragraph has no visible text and contains a page break."""
    if paragraph_el is None or not paragraph_el.tag.endswith("p"):
        return False
    texts = paragraph_el.findall(".//" + qn("w:t"))
    if any((t.text or "").strip() for t in texts):
        return False
    return any(br.get(qn("w:type")) == "page" for br in paragraph_el.findall(".//" + qn("w:br")))


def _remove_trailing_empty_paragraphs(doc: Document) -> None:
    """Strip empty or page-break-only paragraphs from the document tail."""
    body = doc.element.body
    for child in reversed(list(body)):
        if not child.tag.endswith("p"):
            break
        para = Paragraph(child, doc)
        empty = not (para.text or "").strip()
        if not empty and not _paragraph_is_page_break_only(child):
            break
        if not empty:
            break
        parent = child.getparent()
        if parent is not None:
            parent.remove(child)


def _keys_for_formulas(
    sample: SampleRecord,
    by_key: dict[str, TestResultRow],
) -> set[str]:
    """Only tests with saved results get worksheet formula/readings fill."""
    formulas = _worksheet_formulas_for(sample)
    keys = {k for k in by_key if k in formulas and k in TEST_CATALOG}
    if _is_nutrition_sample(sample):
        keys |= {
            k
            for k in by_key
            if k in NUTRITION_PARAGRAPH_FORMULA_TESTS and k in TEST_CATALOG
        }
    return keys


def _conducted_keys(results: list[TestResultRow]) -> set[str]:
    """Tests the analyst actually saved (result and/or worksheet inputs)."""
    keys: set[str] = set()
    for row in results:
        has_value = bool((row.result_value or "").strip())
        has_inputs = any(str(v).strip() for v in (row.inputs or {}).values())
        if has_value or has_inputs:
            keys.add(row.test_key)
    return keys


def _delete_table(table) -> None:
    tbl = table._tbl
    parent = tbl.getparent()
    if parent is not None:
        parent.remove(tbl)


def _summary_rows_for_protocol(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    by_key: dict[str, TestResultRow],
) -> list[tuple[str, str, str, str, str]]:
    """Build page-1 summary rows: conducted tests only (sr, name, method, result, unit)."""
    conducted = _conducted_keys(results)
    rows: list[tuple[str, str, str, str, str]] = []

    app_text = ""
    if "appearance" in by_key:
        app_text = (by_key["appearance"].result_value or "").strip()
    if not app_text:
        app_text = (header.appearance_text or "").strip()
    if app_text:
        rows.append(("1", "Appearance", "", app_text, ""))

    order = catalog_keys_for_category(sample.category)
    sr = len(rows)
    seen: set[str] = set()
    for key in order:
        if key not in conducted or key == "appearance":
            continue
        if key not in by_key:
            continue
        test = TEST_CATALOG.get(key)
        res = by_key[key]
        if not test or not res:
            continue
        sr += 1
        seen.add(key)
        rows.append(
            (
                str(sr),
                test.name,
                test.method,
                res.result_value or "",
                res.unit or "",
            )
        )
    for key in sorted(conducted):
        if key in seen or key == "appearance":
            continue
        res = by_key.get(key)
        test = TEST_CATALOG.get(key) if res else None
        if not res or not test:
            continue
        sr += 1
        rows.append(
            (
                str(sr),
                test.name,
                test.method,
                res.result_value or "",
                res.unit or "",
            )
        )
    return rows


def _fill_water_summary_in_place(
    table,
    by_key: dict[str, TestResultRow],
) -> None:
    """Fill Result/Unit columns in the fixed 11-row water summary; keep template Method."""
    if not table.rows:
        return
    for row_idx, test_key in WATER_SUMMARY_ROWS.items():
        if row_idx >= len(table.rows):
            continue
        row = table.rows[row_idx]
        if len(row.cells) < 4:
            continue
        res = by_key.get(test_key)
        if not res or not (res.result_value or "").strip():
            continue
        result_text = (res.result_value or "").strip()
        _set_cell(row.cells[3], result_text)
        if len(row.cells) >= 5 and (res.unit or "").strip():
            _set_cell(row.cells[4], (res.unit or "").strip())


def _rebuild_summary_table(
    table,
    summary_rows: list[tuple[str, str, str, str, str]],
) -> None:
    """Replace fixed template summary with rows for conducted tests only."""
    if not table.rows:
        return
    while len(table.rows) > 1:
        table._tbl.remove(table.rows[-1]._tr)
    if not summary_rows:
        return
    ncol = len(table.rows[0].cells)
    for sr, name, method, result, unit in summary_rows:
        row = table.add_row()
        cells = row.cells
        if ncol >= 5:
            _set_cell(cells[0], sr)
            _set_cell(cells[1], name)
            _set_cell(cells[2], method)
            _set_cell(cells[3], result)
            _set_cell(cells[4], unit)
        elif ncol >= 4:
            _set_cell(cells[0], sr)
            _set_cell(cells[1], name)
            _set_cell(cells[2], method)
            _set_cell(cells[3], result)


def _prune_worksheet_tables(
    doc: Document,
    blocks: list[tuple[list[int], list[str], list[str]]],
    conducted: set[str],
    *,
    keep_appearance_block: bool = False,
) -> None:
    """Drop worksheet tables (and section titles) for tests that were not conducted."""
    blocks_to_remove: list[tuple[list[int], list[str], list[str]]] = []
    for indices, keys, title_patterns in blocks:
        if keys == ["appearance"]:
            if keep_appearance_block or conducted.intersection(keys):
                continue
        elif conducted.intersection(keys):
            continue
        blocks_to_remove.append((indices, keys, title_patterns))

    if not blocks_to_remove:
        return

    all_tables = list(doc.tables)
    for indices, _keys, title_patterns in sorted(
        blocks_to_remove,
        key=lambda b: max(b[0]),
        reverse=True,
    ):
        tables_in_block = [all_tables[i] for i in indices if i < len(all_tables)]
        if title_patterns and tables_in_block:
            # Use the worksheet table (last in block), not the repeat header.
            title_table = tables_in_block[-1]
            para = _section_title_paragraph_before_table(
                doc, title_table, title_patterns
            )
            if para:
                _delete_paragraph(para)
        for table in reversed(tables_in_block):
            _delete_table(table)


def _remove_repeat_protocol_headers(doc: Document) -> None:
    """Remove mini Protocol No repeat tables between worksheet sections."""
    all_tables = list(doc.tables)
    for table in reversed(all_tables):
        if table is all_tables[0]:
            continue
        if _is_repeat_protocol_header_table(table):
            _delete_table(table)


def _apply_keep_with_next_to_row(row, *, skip_if_last: bool) -> None:
    """Chain row paragraphs with keepWithNext so blocks stay on one page."""
    if skip_if_last:
        return
    for cell in row.cells:
        for para in cell.paragraphs:
            if (para.text or "").strip():
                _set_paragraph_keep_with_next(para)


def _section_title_paragraph_for_table(doc: Document, table) -> Paragraph | None:
    """Return the non-empty section title paragraph immediately above a table."""
    prev = table._tbl.getprevious()
    while prev is not None:
        if prev.tag.endswith("tbl"):
            break
        if prev.tag.endswith("p"):
            para = Paragraph(prev, doc)
            text = (para.text or "").strip()
            if text and text != "Result Table:" and not _is_observation_heading(text):
                if text.endswith(":") or "dry basis" in text.lower():
                    return para
                return None
        prev = prev.getprevious()
    return None


def _apply_worksheet_page_layout(doc: Document) -> None:
    """
    Keep each observation section (title + table) on one page.

    cantSplit on every row; keepWithNext on section titles and all rows except
    the last row in each worksheet / appearance table.
    """
    worksheet_tbls = {t._tbl for t in doc.tables if _is_worksheet_table(t)}
    appearance_tbls = {t._tbl for t in doc.tables if _is_appearance_only_table(t)}
    block_tbls = worksheet_tbls | appearance_tbls
    body_children = list(doc.element.body)

    for i, child in enumerate(body_children):
        if child.tag.split("}")[-1] != "tbl":
            continue
        if child not in block_tbls:
            continue

        table = Table(child, doc)
        _apply_worksheet_cell_padding(table)
        row_count = len(table.rows)
        for ri, row in enumerate(table.rows):
            _set_row_cant_split(row)
            _apply_keep_with_next_to_row(row, skip_if_last=(ri >= row_count - 1))

        title_para = _section_title_paragraph_for_table(doc, table)
        if title_para is not None:
            _set_paragraph_keep_with_next(title_para)
        elif i > 0 and body_children[i - 1].tag.split("}")[-1] == "p":
            para = Paragraph(body_children[i - 1], doc)
            text = (para.text or "").strip()
            if text and _is_observation_heading(text):
                _set_paragraph_keep_with_next(para)


def _fill_water_chloride_readings(table, res: TestResultRow) -> None:
    """Chlorides worksheet row 2 holds both V1 and V2 burette readings."""
    if len(table.rows) < 3 or len(table.rows[2].cells) < 2:
        return
    inputs = res.inputs or {}
    for col_idx, bucket in (
        (1, primary_inputs(inputs)),
        (2, recalc_inputs(inputs)),
    ):
        if not bucket:
            continue
        v1 = bucket.get("v1")
        v2 = bucket.get("v2")
        parts = []
        if v1 is not None and str(v1).strip():
            parts.append(f"V1={_fmt_num(v1)}")
        if v2 is not None and str(v2).strip():
            parts.append(f"V2={_fmt_num(v2)}")
        if parts and col_idx < len(table.rows[2].cells):
            _set_cell(table.rows[2].cells[col_idx], ", ".join(parts))


def _fill_nutrition_sugar_formula_row(
    row,
    by_key: dict[str, TestResultRow],
    ctx: dict[str, float],
) -> None:
    """
    Basic Nutrition sugar row: keep template paragraph formulas; fill worked lines.

    Template row mirrors Jaggery invert / reducing / sucrose paragraph slots.
    Maps bn_total_sugar → invert block, bn_added_sugar → reducing block.
    """
    if not row.cells:
        return

    cell = row.cells[0]
    paras = cell.paragraphs
    if not paras:
        return

    if "bn_total_sugar" in by_key:
        res = by_key["bn_total_sugar"]
        inputs = res.inputs or {}
        worked = worked_formula_lines(
            "bn_total_sugar", inputs, ctx, res.result_value or ""
        )
        line = "\n".join(worked) if worked else ""
        ans = _answer_text(res)
        if ans and ans not in line:
            line = f"{line}\n{ans}".strip()
        if len(paras) > 2:
            _set_paragraph_text(paras[2], line)

    if "bn_added_sugar" in by_key:
        res = by_key["bn_added_sugar"]
        inputs = res.inputs or {}
        worked = worked_formula_lines(
            "bn_added_sugar", inputs, ctx, res.result_value or ""
        )
        line = "\n".join(worked) if worked else ""
        ans = _answer_text(res)
        if ans and ans not in line:
            line = f"{line}\n{ans}".strip()
        if len(paras) > 9:
            _set_paragraph_text(paras[9], line)
        elif len(paras) > 2:
            _set_paragraph_text(paras[2], line)

    if len(row.cells) >= 3 and row.cells[0]._tc is not row.cells[2]._tc:
        reading_parts: list[str] = []
        for key in ("bn_added_sugar", "bn_total_sugar"):
            if key not in by_key:
                continue
            res = by_key[key]
            worked = worked_formula_lines(
                key, res.inputs or {}, ctx, res.result_value or ""
            )
            reading_parts.extend(worked)
        if reading_parts:
            _set_reading_cell(row, 2, "\n\n".join(reading_parts))


def _fill_nutrition_paragraph_formulas(
    doc: Document,
    by_key: dict[str, TestResultRow],
    ctx: dict[str, float],
) -> None:
    """
    Fill worked calculation lines for protein / carbohydrate / energy paragraphs.

    Template stores these formulas as body paragraphs between worksheet tables.
    """
    if "bn_protein" in by_key:
        res = by_key["bn_protein"]
        inputs = res.inputs or {}
        worked = worked_formula_lines(
            "bn_protein", inputs, ctx, res.result_value or ""
        )
        if worked:
            for para in doc.paragraphs:
                text = para.text or ""
                lower = text.lower()
                if (
                    "nitrogen content" in lower
                    or "normality of naoh" in lower
                    or "normality of hcl" in lower
                ):
                    _set_paragraph_text(para, worked[0])
                    break
            for para in doc.paragraphs:
                text = para.text or ""
                if text.strip().lower().startswith("total protein") and len(worked) > 1:
                    _set_paragraph_text(para, f"{text.strip()}\n{worked[1]}")
                    break

    if "bn_carbohydrate" in by_key:
        res = by_key["bn_carbohydrate"]
        worked = worked_formula_lines(
            "bn_carbohydrate", res.inputs or {}, ctx, res.result_value or ""
        )
        if worked:
            for para in doc.paragraphs:
                text = para.text or ""
                if "moisture + ash + fat + protein" in text.lower():
                    symbolic = nutrition_formula_display("bn_carbohydrate")
                    _set_paragraph_text(para, f"{symbolic}\n{worked[0]}")
                    break

    if "bn_calories" in by_key:
        res = by_key["bn_calories"]
        worked = worked_formula_lines(
            "bn_calories", res.inputs or {}, ctx, res.result_value or ""
        )
        if worked:
            for para in doc.paragraphs:
                text = para.text or ""
                lower = text.lower()
                if "(protein + carbohydrate)" in lower or (
                    "protein" in lower and "carbohydrate" in lower and "x 4" in lower
                ):
                    symbolic = nutrition_formula_display("bn_calories")
                    _set_paragraph_text(para, f"{symbolic}\n{worked[0]}")
                    break


def _fill_worksheet_result_cells(
    tables,
    by_key: dict[str, TestResultRow],
) -> None:
    """Write saved result values into simple result-only worksheet cells."""
    for test_key, (t_idx, row_idx, col_idx) in WORKSHEET_RESULT_CELLS.items():
        res = by_key.get(test_key)
        if not res:
            continue
        value = (res.result_value or "").strip()
        if not value:
            value = str((res.inputs or {}).get("color_result") or "").strip()
        if not value:
            continue
        if t_idx >= len(tables):
            continue
        table = tables[t_idx]
        if row_idx >= len(table.rows):
            continue
        row = table.rows[row_idx]
        if col_idx >= len(row.cells):
            continue
        _set_cell(row.cells[col_idx], value)


def _fill_worksheet_readings(
    tables,
    sample: SampleRecord,
    by_key: dict[str, TestResultRow],
) -> None:
    """Write saved input readings into the Readings column."""
    is_water = normalize_category(sample.category) == CATEGORY_WATER
    is_nutrition = _is_nutrition_sample(sample)
    readings_map = _worksheet_readings_for(sample)
    # Include selected formula keys AND any saved result that has a readings map
    # (Jaggery previously only used formula keys; water/nutrition already unioned).
    keys = _keys_for_formulas(sample, by_key)
    keys |= {k for k in by_key if k in readings_map}

    for test_key in keys:
        if test_key in ("invert_sugar", "reducing_sugar", "bn_added_sugar", "bn_total_sugar"):
            continue
        spec = readings_map.get(test_key)
        res = by_key.get(test_key)
        if not spec or not res:
            continue
        t_idx, rows = spec
        if t_idx >= len(tables):
            continue
        table = tables[t_idx]
        inputs = res.inputs or {}

        if is_water and test_key == "chlorides":
            for row_idx, input_key in rows:
                if row_idx >= len(table.rows):
                    continue
                row = table.rows[row_idx]
                if len(row.cells) < 2:
                    continue
                _fill_input_reading_cells(row, 1, inputs, test_key, input_key)
            _fill_water_chloride_readings(table, res)
            continue

        for row_idx, input_key in rows:
            if row_idx >= len(table.rows):
                continue
            row = table.rows[row_idx]
            reading_col = 2 if (is_water and len(row.cells) >= 3 and test_key in ("ph", "odor", "turbidity", "conductivity")) else 1
            if len(row.cells) <= reading_col:
                continue
            primary = primary_inputs(inputs)
            recalc = recalc_inputs(inputs)
            if primary.get(input_key) is None and recalc.get(input_key) is None:
                continue
            _fill_input_reading_cells(row, reading_col, inputs, test_key, input_key)

    if is_water:
        return

    if is_nutrition:
        if len(tables) > 10 and (
            "bn_added_sugar" in keys or "bn_total_sugar" in keys
        ):
            table = tables[10]
            for row_idx, prefer_key, input_key in NUTRITION_SUGAR_READINGS:
                if row_idx >= len(table.rows) or len(table.rows[row_idx].cells) < 3:
                    continue
                used_key = prefer_key
                res = None
                for candidate in (prefer_key, "bn_added_sugar", "bn_total_sugar"):
                    candidate_res = by_key.get(candidate)
                    if not candidate_res:
                        continue
                    merged = candidate_res.inputs or {}
                    primary = primary_inputs(merged)
                    recalc = recalc_inputs(merged)
                    has_val = (
                        primary.get(input_key) is not None
                        or recalc.get(input_key) is not None
                    )
                    if not has_val and input_key == "sample_wt":
                        has_val = (
                            primary.get("sample_wt") is not None
                            or recalc.get("sample_wt") is not None
                        )
                    if has_val:
                        res = candidate_res
                        used_key = candidate
                        break
                if res is None:
                    continue
                _fill_input_reading_cells(
                    table.rows[row_idx], 2, res.inputs or {}, used_key, input_key
                )
        if "bn_protein" in by_key and len(tables) > 6:
            res = by_key["bn_protein"]
            inputs = res.inputs or {}
            titrant = protein_titrant_from(inputs)
            norm_key = protein_normality_key(titrant)
            table = tables[6]
            norm_row = 2 if titrant == "NaOH" else 3
            if norm_row < len(table.rows) and len(table.rows[norm_row].cells) > 1:
                _fill_input_reading_cells(
                    table.rows[norm_row], 1, inputs, "bn_protein", norm_key
                )
        return

    # Shared sugar readings table (Jaggery only)
    if len(tables) > 12 and (
        "invert_sugar" in keys or "reducing_sugar" in keys
    ):
        table = tables[12]
        for row_idx, prefer_key, input_key in SUGAR_READINGS:
            if row_idx >= len(table.rows) or len(table.rows[row_idx].cells) < 3:
                continue
            used_key = prefer_key
            res = None
            for candidate in (prefer_key, "invert_sugar", "reducing_sugar"):
                candidate_res = by_key.get(candidate)
                if not candidate_res:
                    continue
                merged = candidate_res.inputs or {}
                primary = primary_inputs(merged)
                recalc = recalc_inputs(merged)
                has_val = (
                    primary.get(input_key) is not None
                    or recalc.get(input_key) is not None
                )
                if not has_val and input_key == "sample_wt":
                    has_val = (
                        primary.get("sample_wt") is not None
                        or recalc.get("sample_wt") is not None
                    )
                if has_val:
                    res = candidate_res
                    used_key = candidate
                    break
            if res is None:
                continue
            _fill_input_reading_cells(
                table.rows[row_idx], 2, res.inputs or {}, used_key, input_key
            )


def _fill_worksheet_formulas(
    tables,
    sample: SampleRecord,
    by_key: dict[str, TestResultRow],
) -> None:
    """
    Overwrite worksheet formula rows with symbolic formula + worked line,
    and put the final answer in the % / result cell.
    """
    keys = _keys_for_formulas(sample, by_key)
    if not keys:
        return

    ctx = _result_context(by_key)
    formulas_map = _worksheet_formulas_for(sample)
    is_water = normalize_category(sample.category) == CATEGORY_WATER
    is_nutrition = _is_nutrition_sample(sample)

    if is_nutrition:
        selected_or_saved = set(sample.selected_test_keys()) | set(by_key.keys())
        if any(k in selected_or_saved for k in ("bn_added_sugar", "bn_total_sugar")):
            if len(tables) > 10 and len(tables[10].rows) > 6:
                _fill_nutrition_sugar_formula_row(tables[10].rows[6], by_key, ctx)
    elif not is_water:
        # Sugar table row 6: separate Invert (×100) / Reducing (×10) / Sucrose (×0.95)
        selected_or_saved = set(sample.selected_test_keys()) | set(by_key.keys())
        sugar_relevant = any(
            k in selected_or_saved
            for k in ("invert_sugar", "reducing_sugar", "sucrose")
        )
        if sugar_relevant and len(tables) > 12:
            table = tables[12]
            if len(table.rows) > 6:
                _fill_sugar_formula_row(table.rows[6], by_key, ctx)

    for test_key in keys:
        if test_key in NUTRITION_PARAGRAPH_FORMULA_TESTS:
            continue
        if test_key in ("invert_sugar", "reducing_sugar", "bn_added_sugar", "bn_total_sugar"):
            continue
        spec = formulas_map.get(test_key)
        try:
            test = get_test(test_key)
        except KeyError:
            continue
        res = by_key.get(test_key)
        # Only overwrite worksheet formula/answer rows when a result was saved
        if not spec or not res:
            continue
        t_idx, row_indices = spec
        if t_idx >= len(tables):
            continue
        table = tables[t_idx]
        display_formula = (
            nutrition_formula_display(test_key, res.inputs or {})
            if test_key.startswith("bn_")
            else test.formula_display
        )
        lines = _formula_lines(display_formula)
        inputs = res.inputs or {}
        primary = primary_inputs(inputs)
        recalc = recalc_inputs(inputs)
        unit = (res.unit or "") or "%"

        column_sets: list[tuple[dict[str, Any], str, int]] = []
        primary_rv = (
            _computed_result_value(test, test_key, primary, ctx)
            if recalc
            else (res.result_value or "").strip()
        )
        column_sets.append((primary, primary_rv, 1))
        if recalc:
            column_sets.append(
                (recalc, (res.result_value or "").strip(), 2)
            )

        for work_inputs, result_value, reading_col in column_sets:
            worked = worked_formula_lines(
                test_key, work_inputs, ctx, result_value or ""
            )
            answer = _answer_from_value(result_value, unit)

            for i, ri in enumerate(row_indices):
                if ri >= len(table.rows):
                    continue
                row = table.rows[ri]
                if not row.cells:
                    continue
                symbolic = lines[i] if i < len(lines) else display_formula
                existing_desc = _cell_text(row.cells[0]).strip()
                if not existing_desc:
                    _set_cell(row.cells[0], symbolic)
                elif not is_nutrition:
                    _set_cell(row.cells[0], symbolic)
                elif len(row_indices) > 1 and i == len(row_indices) - 1:
                    _set_cell(row.cells[0], symbolic)
                _set_cell_no_wrap(row.cells[0])

                worked_line = worked[i] if i < len(worked) else ""
                is_final = len(row_indices) == 1 or i == len(row_indices) - 1
                is_dual_first = len(row_indices) > 1 and i == 0
                reading_text = _formula_readings_text(
                    worked_line,
                    answer if is_final else "",
                    unit,
                    is_final_row=is_final,
                    is_dual_first_row=is_dual_first,
                )
                if reading_text:
                    _set_reading_cell(row, reading_col, reading_text)


def _fill_jaggery_header_and_summary(
    tables,
    sample: SampleRecord,
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> None:
    # Table 0 — Protocol No | Sample Issued to | Sample Issued by
    if len(tables) >= 1:
        t0 = tables[0]
        cells = t0.rows[0].cells
        if len(cells) >= 6:
            _set_cell(cells[0], "Protocol No")
            _set_cell(cells[1], header.protocol_no or "")
            _set_cell(cells[2], "Sample Issued to")
            _set_cell(cells[3], header.issued_to or "")
            _set_cell(cells[4], "Sample Issued by")
            _set_cell(cells[5], header.issued_by or "")

    # Table 1 — Sample Name / Received On / Lab Code / Date of Analysis
    # Layout: Label | Value | Label | Value
    if len(tables) >= 2:
        t1 = tables[1]
        if len(t1.rows) >= 2 and len(t1.rows[0].cells) >= 4:
            _set_cell(t1.rows[0].cells[0], "Sample Name:")
            _set_cell(t1.rows[0].cells[1], sample.sample_name or "")
            _set_cell(t1.rows[0].cells[2], "Sample Received On:")
            _set_cell(t1.rows[0].cells[3], _fmt_date(header.sample_received_on))
            _set_cell(t1.rows[1].cells[0], "Lab Code No")
            _set_cell(
                t1.rows[1].cells[1],
                sample.lab_code or sample.sample_code or "",
            )
            _set_cell(t1.rows[1].cells[2], "Date of Analysis:")
            _set_cell(t1.rows[1].cells[3], _analysis_date_display(header))

    # Table 2 summary rebuilt in fill_protocol_docx_bytes (conducted tests only).


def _fill_water_header_and_summary(
    tables,
    sample: SampleRecord,
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> None:
    if len(tables) >= 1:
        t0 = tables[0]
        if len(t0.rows) >= 1 and len(t0.rows[0].cells) >= 7:
            cells = t0.rows[0].cells
            _set_cell(cells[1], header.protocol_no or "")
            _set_cell(cells[4], header.issued_to or "")
            _fill_water_issued_by_cell(cells[5], header.issued_by)
        # Row 2/3 (merged): Label|Label|Value|Value|Label|Label|Value|Value
        if len(t0.rows) >= 4 and len(t0.rows[2].cells) >= 8:
            _set_cell(t0.rows[2].cells[0], "Sample Name:")
            _set_cell(t0.rows[2].cells[3], sample.sample_name or "")
            _set_cell(t0.rows[2].cells[4], "Sample Received On:")
            _set_cell(t0.rows[2].cells[7], _fmt_date(header.sample_received_on))
            _set_cell(t0.rows[3].cells[0], "Lab Code No")
            _set_cell(
                t0.rows[3].cells[3],
                sample.lab_code or sample.sample_code or "",
            )
            _set_cell(t0.rows[3].cells[4], "Date of Analysis:")
            _set_cell(t0.rows[3].cells[7], _analysis_date_display(header))

    # Table 1 summary rebuilt in fill_protocol_docx_bytes (conducted tests only).


def _insert_table_row_at(table, index: int):
    """Insert a shallow copy of the row at ``index`` (preserves column count)."""
    src = table.rows[index]._tr
    new_tr = deepcopy(src)
    table._tbl.insert(index, new_tr)
    return table.rows[index]


def _fill_nutrition_protocol_identity_row(table, header: ProtocolHeader) -> None:
    """Prepend protocol / issued-to / issued-by rows to the nutrition header table."""
    if not table.rows:
        return
    _insert_table_row_at(table, 0)
    _insert_table_row_at(table, 0)
    if len(table.rows[0].cells) >= 4:
        _set_cell(table.rows[0].cells[0], "Protocol No")
        _set_cell(table.rows[0].cells[1], header.protocol_no or "")
        _set_cell(table.rows[0].cells[2], "Sample Issued to")
        _set_cell(table.rows[0].cells[3], header.issued_to or "")
    if len(table.rows[1].cells) >= 2:
        _set_cell(table.rows[1].cells[0], "Sample Issued by")
        _set_cell(table.rows[1].cells[1], header.issued_by or "")
        if len(table.rows[1].cells) >= 4:
            _set_cell(table.rows[1].cells[2], "")
            _set_cell(table.rows[1].cells[3], "")


def _fill_nutrition_header_and_summary(
    tables,
    sample: SampleRecord,
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> None:
    if len(tables) >= 1 and len(tables[0].rows) >= 2:
        t0 = tables[0]
        _fill_nutrition_protocol_identity_row(t0, header)
        if len(t0.rows) >= 4 and len(t0.rows[2].cells) >= 4:
            _set_cell(t0.rows[2].cells[0], "Sample Name")
            _set_cell(t0.rows[2].cells[1], sample.sample_name or "")
            _set_cell(t0.rows[2].cells[2], "Sample Received on")
            _set_cell(t0.rows[2].cells[3], _fmt_date(header.sample_received_on))
            _set_cell(t0.rows[3].cells[0], "Lab Code")
            _set_cell(
                t0.rows[3].cells[1],
                sample.lab_code or sample.sample_code or "",
            )
            _set_cell(t0.rows[3].cells[2], "Date of Analysis")
            _set_cell(t0.rows[3].cells[3], _analysis_date_display(header))

    # Table 1 summary rebuilt in fill_protocol_docx_bytes (conducted tests only).


WATER_MICRO_OBSERVATION_ROWS: list[tuple[str, str, str]] = [
    ("1", "water_total_coliform", "Total Coliform"),
    ("2", "water_e_coli", "E. coli"),
]


def _append_water_micro_observation_page(
    doc: Document,
    sample: SampleRecord,
    header: ProtocolHeader,
    by_key: dict[str, TestResultRow],
) -> None:
    """Append the water micro Observation Table as the last protocol page."""
    doc.add_page_break()

    identity = doc.add_paragraph()
    identity.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = identity.add_run(
        f"Lab Code No\t{(sample.lab_code or sample.sample_code or '').strip()}\t"
        f"Date of Analysis:\t{_analysis_date_display(header)}"
    )
    _apply_run_font(run, *PROTOCOL_HEADER_FONT)

    title = doc.add_paragraph()
    title_run = title.add_run("OBSERVATION TABLE:")
    _apply_run_font(title_run, *RESULT_TABLE_TITLE_FONT, bold=True)

    table = doc.add_table(rows=1 + len(WATER_MICRO_OBSERVATION_ROWS), cols=4)
    headers = ("Sr.No", "Name of test", "Procedure", "Result")
    for col_idx, label in enumerate(headers):
        _set_cell(table.rows[0].cells[col_idx], label)

    for row_idx, (sr_no, test_key, display_name) in enumerate(
        WATER_MICRO_OBSERVATION_ROWS, start=1
    ):
        row = table.rows[row_idx]
        res = by_key.get(test_key)
        procedure = ""
        result = ""
        if res:
            procedure = str((res.inputs or {}).get("procedure") or "").strip()
            result = str(res.result_value or "").strip()
            if not result:
                result = str((res.inputs or {}).get("result_obs") or "").strip()
        if not procedure:
            procedure = default_water_micro_procedure(test_key)
        test = get_test(test_key)
        name = test.name if test else display_name
        _set_cell(row.cells[0], sr_no)
        _set_cell(row.cells[1], name)
        _set_cell(row.cells[2], procedure)
        _set_cell(row.cells[3], result)


def append_protocol_disclaimer(doc: Document, header: ProtocolHeader) -> None:
    """Append analyst-editable disclaimer below the protocol body."""
    lines = format_protocol_disclaimer_paragraphs(header.protocol_disclaimer_text)
    if not lines:
        return
    doc.add_paragraph("")
    for line in lines:
        para = doc.add_paragraph(line)
        if line.strip().lower().startswith("disclaimer"):
            for run in para.runs:
                run.bold = True


def fill_protocol_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """
    Produce a filled protocol .docx for download.
    """
    header.issued_to = _protocol_issued_to(sample, header)

    template = _template_path(sample)
    if not template.exists():
        raise FileNotFoundError(f"Protocol template missing: {template}")

    doc = Document(io.BytesIO(template.read_bytes()))
    tables = doc.tables
    by_key = {r.test_key: r for r in results}
    is_water = normalize_category(sample.category) == CATEGORY_WATER
    is_nutrition = _is_nutrition_sample(sample)
    is_food_house_style = not is_water

    if is_water:
        _fill_water_header_and_summary(tables, sample, header, by_key)
    elif is_nutrition:
        _fill_nutrition_header_and_summary(tables, sample, header, by_key)
    else:
        _fill_jaggery_header_and_summary(tables, sample, header, by_key)

    # Worksheet readings + formula / worked / answer (conducted tests only)
    _fill_worksheet_readings(tables, sample, by_key)
    _fill_worksheet_formulas(tables, sample, by_key)
    if not is_water and not is_nutrition:
        _fill_worksheet_result_cells(tables, by_key)

    conducted = _conducted_keys(results)
    summary_rows = _summary_rows_for_protocol(sample, header, results, by_key)
    if is_water and len(tables) >= 2:
        _fill_water_summary_in_place(tables[1], by_key)
    elif is_nutrition and len(tables) >= 2:
        _rebuild_summary_table(tables[1], summary_rows)
    elif len(tables) >= 3:
        _rebuild_summary_table(tables[2], summary_rows)

    if is_water:
        _prune_worksheet_tables(doc, WATER_PRUNE_BLOCKS, conducted)
        _remove_orphan_page_break_paragraphs(doc)
    elif is_nutrition:
        _prune_worksheet_tables(doc, NUTRITION_PRUNE_BLOCKS, conducted)
    else:
        _prune_worksheet_tables(doc, JAGGERY_PRUNE_BLOCKS, conducted)

    _remove_repeat_protocol_headers(doc)
    _consolidate_to_single_section(doc)
    letterhead_applied = False
    if is_food_house_style:
        _replace_page1_body_with_reference_layout(doc, sample, header)
        if normalize_report_format(sample.report_format) != REPORT_FORMAT_WITHOUT_LOGO:
            letterhead_applied = _apply_repeating_protocol_header(doc, header)
        if not letterhead_applied:
            _normalize_food_protocol_section_header_spacing(doc)
    _fill_appearance_worksheet_block(doc, header, by_key)
    _clean_bare_unit_placeholders(doc)
    if is_food_house_style:
        _apply_reference_page_margins(doc)
    if is_food_house_style and not is_nutrition:
        _normalize_jaggery_summary_headers(doc, sample)
    if is_food_house_style and not is_nutrition:
        _promote_inline_worksheet_section_titles(doc, conducted)
    if is_food_house_style:
        _normalize_food_worksheet_headers(doc, sample)
    _keep_page1_block_together(doc)
    _ensure_observation_section_starts_page_2(doc)
    if is_food_house_style:
        _remove_body_signature_blocks(doc)
    _renumber_worksheet_section_titles(doc, conducted)
    if is_nutrition:
        _fill_nutrition_paragraph_formulas(doc, by_key, _result_context(by_key))
    _apply_worksheet_page_layout(doc)
    if is_food_house_style:
        _apply_protocol_end_signatures(doc, sample, header)
    if is_food_house_style:
        _normalize_food_protocol_table_widths(doc)
        _normalize_food_protocol_visual_layout(doc)
        _apply_standard_protocol_footer(doc)
        _normalize_food_protocol_footer_layout(doc)
    if is_water or is_food_house_style:
        _ensure_blank_line_before_result_table(doc, sample)
        _normalize_protocol_typography(doc, sample)
    _blank_director_approval(doc)
    if is_water and _water_sample_includes_micro(sample):
        _append_water_micro_observation_page(doc, sample, header, by_key)
    append_protocol_disclaimer(doc, header)
    _remove_trailing_empty_paragraphs(doc)

    from services.docx_layout import finalize_docx_document

    finalize_docx_document(doc, set_qsf=False)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def suggest_protocol_filename(sample: SampleRecord) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (sample.sample_name or sample.sample_code or "sample")
    )
    return f"Protocol_{safe}_{sample.sample_code}.docx"


def unsaved_selected_test_names(
    sample: SampleRecord,
    results: list[TestResultRow],
) -> list[str]:
    """
    Catalog test names selected for the sample but missing a saved result.

    Used as a generate-time warning so worksheet Readings are not left blank.
    """
    saved: set[str] = set()
    for row in results:
        has_value = bool((row.result_value or "").strip())
        has_inputs = any(
            str(v).strip() != "" for v in (row.inputs or {}).values()
        )
        if has_value or has_inputs:
            saved.add(row.test_key)
    missing: list[str] = []
    for key in sample.selected_test_keys():
        if key not in TEST_CATALOG:
            continue
        if key not in saved:
            missing.append(test_unsaved_display_name(key))
    return missing
