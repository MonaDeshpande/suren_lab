"""
services/docx_filler.py
-----------------------
Fill the reference Word template with form data and return .docx bytes.

Template:
  reference/Customer Test Request form LLP.docx

PDF is generated separately via ReportLab (services/pdf_generator.py).
This module serves the Word (.docx) download only.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

from services.ctr_verification import (
    CHECKLIST_TITLE,
    SAMPLE_SECTION_HEADING,
    SAMPLE_TABLE_HEADERS,
    ctr_test_names_for_sample,
    verification_checklist_rows,
)
from services.customers import format_contacts_for_display
from services.requests import (
    SampleRow,
    TestRequestData,
    ctr_parameters_display,
    delivery_mode_is_selected,
)

# Project root = parent of /services
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "reference" / "Customer Test Request form LLP.docx"


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _yes_no_cell(value: Optional[bool]) -> str:
    """
    Match the Word template Yes/No option cell style.

    Template shows both options with spacing; we mark the selected one.
    """
    if value is True:
        return "Yes  [X]                                   No  [ ]"
    if value is False:
        return "Yes  [ ]                                   No  [X]"
    return "Yes  [ ]                                   No  [ ]"


def _service_cell(service_type: str) -> str:
    """Urgent / Regular options as on the Word form."""
    s = (service_type or "").strip().lower()
    urgent = "[X]" if s == "urgent" else "[ ]"
    regular = "[X]" if s == "regular" else "[ ]"
    return f"Urgent\t{urgent}\t\t\tRegular\t{regular}"


def _delivery_cell(mode: str) -> str:
    """Collect / Courier / Email/Whatsapp options as on the Word form."""
    collect = "[X]" if delivery_mode_is_selected(mode, "Collect") else "[ ]"
    courier = "[X]" if delivery_mode_is_selected(mode, "Courier") else "[ ]"
    email = "[X]" if delivery_mode_is_selected(mode, "Email/Whatsapp") else "[ ]"
    return f"Collect\t{collect}\t Courier\t{courier}\t  Email/Whatsapp\t{email}"


def _set_cell_text(cell, text: str) -> None:
    """
    Replace all paragraph text inside a table cell with `text`.

    Keeps the first paragraph (preserves some formatting) and clears extras.
    """
    text = text or ""
    paragraphs = cell.paragraphs
    if not paragraphs:
        cell.text = text
        return

    paragraphs[0].text = text
    for p in paragraphs[1:]:
        p.text = ""


def _append_to_label(cell, label_prefix: str, value: str) -> None:
    """Write 'Label: value' into a cell (template already has the label)."""
    value = value or ""
    _set_cell_text(cell, f"{label_prefix} {value}".strip())


def _add_page_break(doc: Document) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    run.add_break(WD_BREAK.PAGE)


def _trim_table_rows(table: Table, keep_rows: int) -> None:
    """Remove trailing rows from a Word table (keep header + data rows)."""
    while len(table.rows) > keep_rows:
        table._element.remove(table.rows[-1]._element)


def _set_table_borders(table: Table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")
        borders.append(element)
    tbl_pr.append(borders)


def _add_sample_table(doc: Document, sample: SampleRow, sr_index: int) -> Table:
    table = doc.add_table(rows=2, cols=5)
    _set_table_borders(table)
    header_cells = table.rows[0].cells
    for idx, label in enumerate(SAMPLE_TABLE_HEADERS):
        _set_cell_text(header_cells[idx], label)
    data_cells = table.rows[1].cells
    _set_cell_text(data_cells[0], str(sr_index))
    _set_cell_text(data_cells[1], sample.sample_name or "")
    _set_cell_text(data_cells[2], sample.batch_code or "")
    _set_cell_text(data_cells[3], sample.quantity or "")
    _set_cell_text(data_cells[4], ctr_parameters_display(sample))
    return table


def _add_tests_paragraphs(doc: Document, sample: SampleRow) -> None:
    names = ctr_test_names_for_sample(sample)
    if not names:
        return
    doc.add_paragraph("Tests to be performed:")
    for index, name in enumerate(names, start=1):
        doc.add_paragraph(f"{index}. {name}")


def _add_verification_table(doc: Document, sample: SampleRow) -> Table:
    rows = verification_checklist_rows(sample)
    table = doc.add_table(rows=len(rows) + 1, cols=3)
    _set_table_borders(table)
    header = table.rows[0].cells
    _set_cell_text(header[0], "Sr No")
    _set_cell_text(header[1], "Particulars")
    _set_cell_text(header[2], "Remark")
    for row_idx, row in enumerate(rows, start=1):
        cells = table.rows[row_idx].cells
        _set_cell_text(cells[0], str(row.sr))
        _set_cell_text(cells[1], row.particular)
        _set_cell_text(cells[2], row.remark)
    return table


def fill_docx_bytes(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """
    Open the reference template, fill tables, return .docx as bytes.

    Raises
    ------
    FileNotFoundError
        If the Word template is missing from /reference.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Word template not found at: {TEMPLATE_PATH}")

    raw = TEMPLATE_PATH.read_bytes()
    doc = Document(io.BytesIO(raw))

    c = data.customer
    tables = doc.tables

    if len(tables) >= 1:
        t0: Table = tables[0]

        _append_to_label(t0.rows[0].cells[0], "Date:", _fmt_date(data.request_date))
        _append_to_label(t0.rows[0].cells[1], "Lab Code:", data.lab_code or "")

        _set_cell_text(
            t0.rows[1].cells[0],
            f"Customer Details:\n{c.customer_name or ''}",
        )
        _set_cell_text(
            t0.rows[1].cells[1],
            f"Address:\n{c.address or ''}",
        )

        contact_names, contact_emails = format_contacts_for_display(
            c.resolved_contacts()
        )
        _append_to_label(
            t0.rows[2].cells[0],
            "Name of Contact Person:",
            contact_names or c.contact_person or "",
        )
        _append_to_label(
            t0.rows[2].cells[1],
            "Contact Number:",
            c.contact_number or "",
        )

        _append_to_label(
            t0.rows[3].cells[0],
            "Email:",
            contact_emails or c.email or "",
        )
        _append_to_label(
            t0.rows[3].cells[1],
            "GST Number of Customer:",
            c.gst_number or "",
        )

        nos = "" if data.number_of_samples is None else str(data.number_of_samples)
        _append_to_label(t0.rows[4].cells[0], "Number of Samples", nos)

        _set_cell_text(t0.rows[5].cells[0], "Sampling Done by Laboratory:")
        _set_cell_text(t0.rows[5].cells[1], _yes_no_cell(data.sampling_by_lab))

        _append_to_label(
            t0.rows[6].cells[0],
            "Storage Temperature of sample required:",
            data.storage_temperature or "",
        )

        method = data.test_method_spec or ""
        _set_cell_text(
            t0.rows[7].cells[0],
            f"Specific test method/ Specification to be followed:\n{method}".rstrip(),
        )

        _set_cell_text(t0.rows[8].cells[0], "Decision Rule required:")
        _set_cell_text(t0.rows[8].cells[1], _yes_no_cell(data.decision_rule))

        _set_cell_text(t0.rows[9].cells[0], "Service required:")
        _set_cell_text(t0.rows[9].cells[1], _service_cell(data.service_type))

        _set_cell_text(t0.rows[10].cells[0], "Mode of report delivery:")
        _set_cell_text(t0.rows[10].cells[1], _delivery_cell(data.delivery_mode))

        _set_cell_text(t0.rows[11].cells[0], "Payment Details:")
        _set_cell_text(t0.rows[11].cells[1], data.payment_details or "")

    filled = [s for s in data.samples if not s.is_empty()]

    if len(tables) >= 3 and filled:
        t2: Table = tables[2]
        first = filled[0]
        if len(t2.rows) >= 2:
            row = t2.rows[1]
            cells = row.cells
            if len(cells) >= 5:
                _set_cell_text(cells[0], "1")
                _set_cell_text(cells[1], first.sample_name or "")
                _set_cell_text(cells[2], first.batch_code or "")
                _set_cell_text(cells[3], first.quantity or "")
                _set_cell_text(cells[4], ctr_parameters_display(first))
        _trim_table_rows(t2, 2)
        _add_tests_paragraphs(doc, first)

        for index, sample in enumerate(filled[1:], start=2):
            _add_page_break(doc)
            doc.add_paragraph(SAMPLE_SECTION_HEADING)
            _add_sample_table(doc, sample, index)
            _add_tests_paragraphs(doc, sample)

    for sample in filled:
        _add_page_break(doc)
        doc.add_paragraph(CHECKLIST_TITLE)
        _add_verification_table(doc, sample)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def suggest_docx_filename(data: TestRequestData) -> str:
    """Filename for the filled Word download."""
    name = (data.customer.customer_name or "customer").strip()
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
    safe = safe[:40].strip("_") or "customer"
    d = data.request_date.isoformat() if data.request_date else "undated"
    return f"CTR_{safe}_{d}.docx"
