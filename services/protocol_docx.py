"""
services/protocol_docx.py
-------------------------
Fill the protocol Word template with header + page-1 results + appearance
+ catalog formula_display on worksheet formula rows.

Template layout source:
  reference/Jaggery Protocol LLP.docx

Only tests that were selected/saved for THIS sample appear in the result table.
Worksheets for every catalog test stay in the template; we fill what we can.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches

from services.audit import generator_stamp_lines
from services.branding import LOGO_HEIGHT_IN, LOGO_PATH, LOGO_WIDTH_IN
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import TEST_CATALOG
from services.samples import SampleRecord

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "reference" / "Jaggery Protocol LLP.docx"

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


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _set_cell(cell, text: str) -> None:
    text = text or ""
    if not cell.paragraphs:
        cell.text = text
        return
    cell.paragraphs[0].text = text
    for p in cell.paragraphs[1:]:
        p.text = ""


def _formula_lines(formula_display: str) -> list[str]:
    """Split dual formulas on ';' into one line per worksheet row."""
    parts = [p.strip() for p in (formula_display or "").split(";")]
    return [p for p in parts if p]


def _clear_paragraph_drawings(paragraph) -> None:
    """Remove DrawingML / VML shapes from a header paragraph."""
    p = paragraph._p
    for tag in ("w:drawing", "w:pict"):
        for el in p.findall(".//" + qn(tag)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)


def _inject_letterhead_logo(doc: Document) -> None:
    """
    Place assets/logo.png in the section header at the protocol letterhead size
    (~7.25 x 1.42 in), replacing the empty template textbox.
    """
    if not LOGO_PATH.exists():
        return

    for section in doc.sections:
        header = section.header
        # Keep first paragraph; clear leftover empty letterhead shapes
        if header.paragraphs:
            paragraph = header.paragraphs[0]
        else:
            paragraph = header.add_paragraph()

        _clear_paragraph_drawings(paragraph)
        for run in paragraph.runs:
            run.text = ""

        # Drop extra empty paragraphs left by the template
        for extra in header.paragraphs[1:]:
            _clear_paragraph_drawings(extra)
            p_el = extra._element
            parent = p_el.getparent()
            if parent is not None:
                parent.remove(p_el)

        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        run.add_picture(
            str(LOGO_PATH),
            width=Inches(LOGO_WIDTH_IN),
            height=Inches(LOGO_HEIGHT_IN),
        )


def _keys_for_formulas(
    sample: SampleRecord,
    by_key: dict[str, TestResultRow],
) -> set[str]:
    """Selected catalog keys and/or keys with saved results."""
    keys = set(sample.selected_test_keys()) | set(by_key.keys())
    return {k for k in keys if k in WORKSHEET_FORMULAS and k in TEST_CATALOG}


def _fill_worksheet_formulas(
    tables,
    sample: SampleRecord,
    by_key: dict[str, TestResultRow],
) -> None:
    """
    Overwrite worksheet formula rows with TEST_CATALOG formula_display.

    Sugar table (12) is shared by invert + reducing — both go on row 6.
    """
    keys = _keys_for_formulas(sample, by_key)
    if not keys:
        return

    # Sugar table: combine both formulas on the shared row
    sugar_keys = [k for k in ("invert_sugar", "reducing_sugar") if k in keys]
    if sugar_keys and len(tables) > 12:
        lines: list[str] = []
        for k in sugar_keys:
            label = "Invert" if k == "invert_sugar" else "Reducing"
            lines.append(f"{label}: {TEST_CATALOG[k].formula_display}")
        table = tables[12]
        if len(table.rows) > 6 and table.rows[6].cells:
            text = "\n".join(lines)
            for cell in table.rows[6].cells:
                _set_cell(cell, text)

    for test_key in keys:
        if test_key in ("invert_sugar", "reducing_sugar"):
            continue  # handled above
        spec = WORKSHEET_FORMULAS.get(test_key)
        test = TEST_CATALOG.get(test_key)
        if not spec or not test:
            continue
        t_idx, row_indices = spec
        if t_idx >= len(tables):
            continue
        table = tables[t_idx]
        lines = _formula_lines(test.formula_display)
        for i, ri in enumerate(row_indices):
            if ri >= len(table.rows):
                continue
            row = table.rows[ri]
            if not row.cells:
                continue
            formula_text = lines[i] if i < len(lines) else test.formula_display
            _set_cell(row.cells[0], formula_text)


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
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Protocol template missing: {TEMPLATE_PATH}")

    doc = Document(io.BytesIO(TEMPLATE_PATH.read_bytes()))
    _inject_letterhead_logo(doc)
    tables = doc.tables
    by_key = {r.test_key: r for r in results}

    # Table 0 — Protocol No | Sample Issued to | Sample Issued by
    if len(tables) >= 1:
        t0 = tables[0]
        cells = t0.rows[0].cells
        # Template: Protocol No | (value) | Sample Issued to | (value) | Sample Issued by | (value)
        if len(cells) >= 6:
            _set_cell(cells[0], "Protocol No")
            _set_cell(cells[1], header.protocol_no or "")
            _set_cell(cells[2], "Sample Issued to")
            _set_cell(cells[3], header.issued_to or "")
            _set_cell(cells[4], "Sample Issued by")
            _set_cell(cells[5], header.issued_by or "")

    # Table 1 — Sample Name / Received On / Lab Code / Date of Analysis
    if len(tables) >= 2:
        t1 = tables[1]
        if len(t1.rows) >= 2 and len(t1.rows[0].cells) >= 4:
            _set_cell(t1.rows[0].cells[0], f"Sample Name: {sample.sample_name or ''}")
            _set_cell(
                t1.rows[0].cells[2],
                f"Sample Received On: {_fmt_date(header.sample_received_on)}",
            )
            _set_cell(
                t1.rows[1].cells[0],
                f"Lab Code No: {sample.lab_code or sample.sample_code}",
            )
            _set_cell(
                t1.rows[1].cells[2],
                f"Date of Analysis: {_fmt_date(header.date_of_analysis)}",
            )

    # Table 2 — page-1 result summary (fill Result column for known catalog rows)
    if len(tables) >= 3:
        t2 = tables[2]
        # Map row index → test_key by matching name in column 1
        for ri, row in enumerate(t2.rows):
            if ri == 0:
                continue
            cells = row.cells
            if len(cells) < 4:
                continue
            name = (cells[1].text or "").strip().split("\n")[0].strip()
            matched = None
            for key, test in TEST_CATALOG.items():
                if test.name.lower() in name.lower() or name.lower() in test.name.lower():
                    matched = key
                    break
            if matched and matched in by_key:
                res = by_key[matched]
                # Result column ~ index 3
                _set_cell(cells[3], res.result_value or "")

    # Table 4 — Appearance
    if len(tables) >= 5:
        _set_cell(
            tables[4].rows[0].cells[0],
            f"APPEARANCE:\n{header.appearance_text or ''}",
        )

    # Worksheet formula rows ← catalog formula_display
    _fill_worksheet_formulas(tables, sample, by_key)

    # Generator stamp; Checked By / Dated signature stay blank for pen
    doc.add_paragraph("")
    for line in generator_stamp_lines(generated_by, generated_at):
        doc.add_paragraph(line)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def suggest_protocol_filename(sample: SampleRecord) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (sample.sample_name or sample.sample_code or "sample")
    )
    return f"Protocol_{safe}_{sample.sample_code}.docx"
