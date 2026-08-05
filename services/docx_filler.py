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
from docx.table import Table

from services.customers import format_contacts_for_display
from services.requests import TestRequestData, ctr_parameters_display

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
    m = (mode or "").strip().lower()
    collect = "[X]" if m == "collect" else "[ ]"
    courier = "[X]" if m == "courier" else "[ ]"
    email = "[X]" if m in ("email/whatsapp", "email", "whatsapp") else "[ ]"
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

    # Work on an in-memory copy so the original template stays untouched
    raw = TEMPLATE_PATH.read_bytes()
    doc = Document(io.BytesIO(raw))

    c = data.customer
    tables = doc.tables

    # -----------------------------------------------------------------------
    # Table 0 — main request header (12 rows × 2 columns in the template)
    # -----------------------------------------------------------------------
    if len(tables) >= 1:
        t0: Table = tables[0]

        # Row 0: Date | Lab Code
        _append_to_label(t0.rows[0].cells[0], "Date:", _fmt_date(data.request_date))
        _append_to_label(t0.rows[0].cells[1], "Lab Code:", data.lab_code or "")

        # Row 1: Customer Details | Address
        _set_cell_text(
            t0.rows[1].cells[0],
            f"Customer Details:\n{c.customer_name or ''}",
        )
        _set_cell_text(
            t0.rows[1].cells[1],
            f"Address:\n{c.address or ''}",
        )

        # Row 2: Contact person | Contact number
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

        # Row 3: Email | GST
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

        # Row 4: Number of Samples (left cell holds label + value)
        nos = "" if data.number_of_samples is None else str(data.number_of_samples)
        _append_to_label(t0.rows[4].cells[0], "Number of Samples", nos)

        # Row 5: Sampling Done by Laboratory | Yes/No options
        _set_cell_text(t0.rows[5].cells[0], "Sampling Done by Laboratory:")
        _set_cell_text(t0.rows[5].cells[1], _yes_no_cell(data.sampling_by_lab))

        # Row 6: Storage temperature
        _append_to_label(
            t0.rows[6].cells[0],
            "Storage Temperature of sample required:",
            data.storage_temperature or "",
        )

        # Row 7: Specific test method
        method = data.test_method_spec or ""
        _set_cell_text(
            t0.rows[7].cells[0],
            f"Specific test method/ Specification to be followed:\n{method}".rstrip(),
        )

        # Row 8: Decision Rule | Yes/No options
        _set_cell_text(t0.rows[8].cells[0], "Decision Rule required:")
        _set_cell_text(t0.rows[8].cells[1], _yes_no_cell(data.decision_rule))

        # Row 9: Service required | Urgent / Regular
        _set_cell_text(t0.rows[9].cells[0], "Service required:")
        _set_cell_text(t0.rows[9].cells[1], _service_cell(data.service_type))

        # Row 10: Mode of report delivery
        _set_cell_text(t0.rows[10].cells[0], "Mode of report delivery:")
        _set_cell_text(t0.rows[10].cells[1], _delivery_cell(data.delivery_mode))

        # Row 11: Payment Details
        _set_cell_text(t0.rows[11].cells[0], "Payment Details:")
        _set_cell_text(t0.rows[11].cells[1], data.payment_details or "")

    # -----------------------------------------------------------------------
    # Table 2 — sample grid (Sr | Name | Batch | Qty | Parameters)
    # Template has header + ~17 blank rows
    # -----------------------------------------------------------------------
    if len(tables) >= 3:
        t2: Table = tables[2]
        filled = [s for s in data.samples if not s.is_empty()]
        data_row_count = max(0, len(t2.rows) - 1)

        for i, sample in enumerate(filled):
            if i >= data_row_count:
                break
            row = t2.rows[i + 1]
            cells = row.cells
            if len(cells) >= 5:
                _set_cell_text(cells[0], str(i + 1))
                _set_cell_text(cells[1], sample.sample_name or "")
                _set_cell_text(cells[2], sample.batch_code or "")
                _set_cell_text(cells[3], sample.quantity or "")
                _set_cell_text(cells[4], ctr_parameters_display(sample))

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
