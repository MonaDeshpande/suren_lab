"""
services/pdf_generator.py
-------------------------
Generate a filled Customer Test Request PDF that matches the reference Word form.

Primary path (exact layout):
  1. Fill reference/Customer Test Request form LLP.docx
  2. Convert to PDF with docx2pdf (Microsoft Word on Windows)

Fallback (if Word conversion fails):
  ReportLab recreation on Letter size, 1" margins, no custom branding,
  same section order and 17 sample rows as the Word template.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.docx_filler import fill_docx_bytes
from services.requests import SampleRow, TestRequestData
from services.audit import generator_stamp_lines

logger = logging.getLogger(__name__)

# Visual constants — plain form look (fallback only)
BORDER = colors.black
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_SIZE = 11  # close to Word ~12 pt
SMALL = 9


def _yes_no(value: Optional[bool]) -> str:
    if value is True:
        return "Yes  [X]                    No  [ ]"
    if value is False:
        return "Yes  [ ]                    No  [X]"
    return "Yes  [ ]                    No  [ ]"


def _service_marks(service_type: str) -> str:
    urgent = "[X]" if (service_type or "").strip().lower() == "urgent" else "[ ]"
    regular = "[X]" if (service_type or "").strip().lower() == "regular" else "[ ]"
    return f"Urgent  {urgent}          Regular  {regular}"


def _delivery_marks(mode: str) -> str:
    m = (mode or "").strip().lower()
    collect = "[X]" if m == "collect" else "[ ]"
    courier = "[X]" if m == "courier" else "[ ]"
    email = "[X]" if m in ("email/whatsapp", "email", "whatsapp") else "[ ]"
    return f"Collect  {collect}      Courier  {courier}      Email/Whatsapp  {email}"


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    safe = (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Paragraph(safe.replace("\n", "<br/>"), style)


def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """
    Write filled .docx to a temp file, convert with docx2pdf, return PDF bytes.

    Requires Microsoft Word installed on Windows.
    """
    from docx2pdf import convert  # imported here so ReportLab fallback still works

    tmp_dir = tempfile.mkdtemp(prefix="sls_ctr_")
    docx_path = Path(tmp_dir) / "filled_ctr.docx"
    pdf_path = Path(tmp_dir) / "filled_ctr.pdf"

    try:
        docx_path.write_bytes(docx_bytes)
        # docx2pdf uses Word COM; convert(input, output)
        convert(str(docx_path), str(pdf_path))
        if not pdf_path.exists():
            raise RuntimeError("docx2pdf finished but PDF file was not created.")
        return pdf_path.read_bytes()
    finally:
        # Clean temp files best-effort
        for p in (docx_path, pdf_path):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _generate_reportlab_fallback(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """
    Letter-size plain form twin of the Word template (no custom branding/footer).

    Used only when Microsoft Word / docx2pdf conversion is unavailable.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,  # Word template is 8.5 x 11
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        topMargin=1.0 * inch,
        bottomMargin=0.75 * inch,
        title="Customer Test Request Form",
        author="S Testing Laboratory",
    )

    styles = getSampleStyleSheet()
    value = ParagraphStyle(
        "FormValue",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=FONT_SIZE,
        leading=14,
        alignment=TA_LEFT,
    )
    note_style = ParagraphStyle(
        "NoteStyle",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=SMALL,
        leading=12,
        alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "SectionHead",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=FONT_SIZE,
        leading=14,
        spaceBefore=6,
        spaceAfter=4,
    )
    th_style = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=SMALL,
        leading=11,
        alignment=TA_LEFT,
    )
    td_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=SMALL,
        leading=11,
        alignment=TA_LEFT,
    )
    sign_style = ParagraphStyle(
        "SignStyle",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=FONT_SIZE,
        leading=14,
    )

    c = data.customer
    story: list = []
    usable = 6.5 * inch  # letter width minus 1"+1" margins
    col_w = [usable / 2, usable / 2]

    # ----- Main details table (Word Table 0) — plain borders, no tint -----
    main_data = [
        [
            _p(f"<b>Date:</b> {_fmt_date(data.request_date)}", value),
            _p(f"<b>Lab Code:</b> {data.lab_code or ''}", value),
        ],
        [
            _p(f"<b>Customer Details:</b><br/>{c.customer_name or ''}", value),
            _p(
                f"<b>Address:</b><br/>{(c.address or '').replace(chr(10), '<br/>')}",
                value,
            ),
        ],
        [
            _p(f"<b>Name of Contact Person:</b> {c.contact_person or ''}", value),
            _p(f"<b>Contact Number:</b> {c.contact_number or ''}", value),
        ],
        [
            _p(f"<b>Email:</b> {c.email or ''}", value),
            _p(f"<b>GST Number of Customer:</b> {c.gst_number or ''}", value),
        ],
        [
            _p(
                f"<b>Number of Samples</b> "
                f"{'' if data.number_of_samples is None else data.number_of_samples}",
                value,
            ),
            _p("", value),
        ],
        [
            _p("<b>Sampling Done by Laboratory:</b>", value),
            _p(_yes_no(data.sampling_by_lab), value),
        ],
        [
            _p(
                f"<b>Storage Temperature of sample required:</b> "
                f"{data.storage_temperature or ''}",
                value,
            ),
            _p("", value),
        ],
        [
            _p(
                f"<b>Specific test method/ Specification to be followed:</b><br/>"
                f"{data.test_method_spec or ''}",
                value,
            ),
            _p("", value),
        ],
        [
            _p("<b>Decision Rule required:</b>", value),
            _p(_yes_no(data.decision_rule), value),
        ],
        [
            _p("<b>Service required:</b>", value),
            _p(_service_marks(data.service_type), value),
        ],
        [
            _p("<b>Mode of report delivery:</b>", value),
            _p(_delivery_marks(data.delivery_mode), value),
        ],
        [
            _p("<b>Payment Details:</b>", value),
            _p(data.payment_details or "", value),
        ],
    ]

    main_table = Table(main_data, colWidths=col_w, hAlign="LEFT")
    main_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("SPAN", (0, 4), (1, 4)),
                ("SPAN", (0, 6), (1, 6)),
                ("SPAN", (0, 7), (1, 7)),
            ]
        )
    )
    story.append(main_table)
    story.append(Spacer(1, 6))

    # ----- Notes (Word Table 1) -----
    notes = (
        "<b>Note:</b> "
        "1) The samples will be processed only after receiving the advance payment. "
        "2) Kindly pay entire amount if report has to be sent by courier/ email/Whatsapp. "
        "3) Samples will be stored for 7 Days after Report dispatch."
    )
    note_table = Table([[_p(notes, note_style)]], colWidths=[usable])
    note_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(note_table)
    story.append(Spacer(1, 14))

    # ----- Signatures (Word body paragraph) -----
    sign_table = Table(
        [
            [
                _p("Receiver's Sign &amp; date", sign_style),
                _p("Customer Signature &amp; date:", sign_style),
            ]
        ],
        colWidths=col_w,
    )
    story.append(sign_table)
    story.append(Spacer(1, 12))

    # ----- Sample section -----
    story.append(
        Paragraph("Sample Description &amp; tests to be performed:", section_style)
    )

    header = [
        _p("Sr. No", th_style),
        _p("Name of sample", th_style),
        _p("Code/batch no.", th_style),
        _p("Sample qty.", th_style),
        _p("Parameters", th_style),
    ]

    filled = [s for s in data.samples if not s.is_empty()]
    display_rows: list[SampleRow] = list(filled)
    # Word template has 17 data rows
    while len(display_rows) < 17:
        display_rows.append(SampleRow(sr_no=len(display_rows) + 1))

    body = []
    for i, s in enumerate(display_rows, start=1):
        # Show serial number only on rows that contain sample data
        sr = str(i) if not s.is_empty() else ""
        body.append(
            [
                _p(sr, td_style),
                _p(s.sample_name or "", td_style),
                _p(s.batch_code or "", td_style),
                _p(s.quantity or "", td_style),
                _p(s.parameters or "", td_style),
            ]
        )

    sample_table = Table(
        [header] + body,
        colWidths=[
            0.55 * inch,
            1.7 * inch,
            1.35 * inch,
            1.0 * inch,
            usable - (0.55 + 1.7 + 1.35 + 1.0) * inch,
        ],
        hAlign="LEFT",
        repeatRows=1,
    )
    sample_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(sample_table)

    # Generator stamp (receiver / customer signs stay blank for pen)
    story.append(Spacer(1, 14))
    stamp_style = ParagraphStyle(
        "Stamp",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=SMALL,
        leading=12,
        alignment=TA_LEFT,
    )
    for line in generator_stamp_lines(generated_by, generated_at):
        story.append(Paragraph(line.replace("&", "&amp;"), stamp_style))

    doc.build(story)
    return buffer.getvalue()


def generate_pdf_bytes(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """
    Build the filled Customer Test Request PDF.

    Prefers Word-template → PDF (exact match). Falls back to ReportLab twin.
    """
    docx_bytes = fill_docx_bytes(
        data, generated_by=generated_by, generated_at=generated_at
    )

    try:
        pdf_bytes = _convert_docx_to_pdf_bytes(docx_bytes)
        if pdf_bytes and pdf_bytes[:4] == b"%PDF":
            return pdf_bytes
        raise RuntimeError("Converted file does not look like a PDF.")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Word→PDF conversion failed (%s); using ReportLab fallback.",
            exc,
        )
        return _generate_reportlab_fallback(
            data, generated_by=generated_by, generated_at=generated_at
        )


def suggest_pdf_filename(data: TestRequestData) -> str:
    """Build a filesystem-safe download filename."""
    name = (data.customer.customer_name or "customer").strip()

    def _safe(text: str) -> str:
        cleaned = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text
        )
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_")

    safe = _safe(name)[:40] or "customer"
    d = data.request_date.isoformat() if data.request_date else "undated"
    lab = _safe((data.lab_code or "").strip())
    parts = ["CTR", safe, d]
    if lab:
        parts.append(lab[:30])
    return "_".join(parts) + ".pdf"
