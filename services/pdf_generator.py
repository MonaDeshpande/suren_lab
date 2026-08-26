"""
services/pdf_generator.py
-------------------------
Generate a filled Customer Test Request PDF via ReportLab.

Layout mirrors reference/Customer Test Request form LLP.docx:
  Page 1 — request header table, notes, signature lines
  Pages 2+ — one sample per page (single-row table + tests list)
  Final pages — per-sample Sample Verification Checklist (table 1 only)

Word (.docx) download is handled separately by services/docx_filler.py.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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

# Visual constants — plain form look matching LLP template
BORDER = colors.black
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_SIZE = 11  # Word template labels ~12 pt
SMALL = 9
FOOTER_TEXT = "[Control copy]"
SAMPLE_HEADER_HEIGHT = 0.35 * inch
SAMPLE_ROW_HEIGHT = 0.30 * inch


def _yes_no(value: Optional[bool]) -> str:
    if value is True:
        return "Yes  [X]                                   No  [ ]"
    if value is False:
        return "Yes  [ ]                                   No  [X]"
    return "Yes  [ ]                                   No  [ ]"


def _service_marks(service_type: str) -> str:
    urgent = "[X]" if (service_type or "").strip().lower() == "urgent" else "[ ]"
    regular = "[X]" if (service_type or "").strip().lower() == "regular" else "[ ]"
    return f"Urgent  {urgent}          Regular  {regular}"


def _delivery_marks(mode: str) -> str:
    collect = "[X]" if delivery_mode_is_selected(mode, "Collect") else "[ ]"
    courier = "[X]" if delivery_mode_is_selected(mode, "Courier") else "[ ]"
    email = "[X]" if delivery_mode_is_selected(mode, "Email/Whatsapp") else "[ ]"
    return f"Collect  {collect}      Courier  {courier}      Email/Whatsapp  {email}"


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    """Plain user text — escape HTML metacharacters."""
    return Paragraph(_escape(text).replace("\n", "<br/>"), style)


def _lv(label: str, value: str, style: ParagraphStyle) -> Paragraph:
    """Bold label plus escaped value on the same line."""
    body = f"<b>{_escape(label)}</b>"
    if value:
        body = f"{body} {_escape(value)}"
    return Paragraph(body, style)


def _lv_br(label: str, value: str, style: ParagraphStyle) -> Paragraph:
    """Bold label, line break, then escaped value (may contain newlines)."""
    val = _escape(value).replace("\n", "<br/>")
    return Paragraph(f"<b>{_escape(label)}</b><br/>{val}", style)


def _draw_footer(canvas, doc) -> None:
    """Match LLP.docx footer on every page."""
    canvas.saveState()
    canvas.setFont(FONT, 10)
    canvas.drawString(doc.leftMargin, 0.45 * inch, FOOTER_TEXT)
    canvas.restoreState()


def _sample_col_widths(usable: float) -> list[float]:
    return [
        0.55 * inch,
        1.7 * inch,
        1.35 * inch,
        1.0 * inch,
        usable - (0.55 + 1.7 + 1.35 + 1.0) * inch,
    ]


def _build_one_sample_table(
    sample: SampleRow,
    sr_index: int,
    usable: float,
    th_style: ParagraphStyle,
    td_style: ParagraphStyle,
) -> Table:
    header = [_p(label, th_style) for label in SAMPLE_TABLE_HEADERS]
    body = [
        [
            _p(str(sr_index), td_style),
            _p(sample.sample_name or "", td_style),
            _p(sample.batch_code or "", td_style),
            _p(sample.quantity or "", td_style),
            _p(ctr_parameters_display(sample), td_style),
        ]
    ]
    sample_table = Table(
        [header] + body,
        colWidths=_sample_col_widths(usable),
        rowHeights=[SAMPLE_HEADER_HEIGHT, SAMPLE_ROW_HEIGHT],
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
    return sample_table


def _build_tests_block(
    sample: SampleRow,
    td_style: ParagraphStyle,
) -> list:
    names = ctr_test_names_for_sample(sample)
    if not names:
        return []
    blocks: list = [Spacer(1, 8), _p("Tests to be performed:", td_style)]
    for index, name in enumerate(names, start=1):
        blocks.append(_p(f"{index}. {name}", td_style))
    return blocks


def _build_verification_table(
    sample: SampleRow,
    usable: float,
    th_style: ParagraphStyle,
    td_style: ParagraphStyle,
) -> Table:
    header = [
        _p("Sr No", th_style),
        _p("Particulars", th_style),
        _p("Remark", th_style),
    ]
    rows = verification_checklist_rows(sample)
    body = [
        [
            _p(str(row.sr), td_style),
            _p(row.particular, td_style),
            _p(row.remark, td_style),
        ]
        for row in rows
    ]
    table = Table(
        [header] + body,
        colWidths=[0.55 * inch, 2.6 * inch, usable - 3.15 * inch],
        hAlign="LEFT",
        repeatRows=1,
    )
    table.setStyle(
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
    return table


def _generate_ctr_pdf(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """
    Letter-size CTR: header page, one sample per page, checklist per sample.

    generated_by / generated_at are accepted for API compatibility but are
    not printed on the CTR form (pen signatures stay on template blanks).
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
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
    contact_names, contact_emails = format_contacts_for_display(c.resolved_contacts())
    story: list = []
    usable = 6.5 * inch
    col_w = [usable / 2, usable / 2]

    # ----- Page 1: main details table (Word Table 0) -----
    main_data = [
        [
            _lv("Date:", _fmt_date(data.request_date), value),
            _lv("Lab Code:", data.lab_code or "", value),
        ],
        [
            _lv_br("Customer Details:", c.customer_name or "", value),
            _lv_br("Address:", c.address or "", value),
        ],
        [
            _lv(
                "Name of Contact Person:",
                contact_names or c.contact_person or "",
                value,
            ),
            _lv("Contact Number:", c.contact_number or "", value),
        ],
        [
            _lv("Email:", contact_emails or c.email or "", value),
            _lv("GST Number of Customer:", c.gst_number or "", value),
        ],
        [
            _lv(
                "Number of Samples",
                "" if data.number_of_samples is None else str(data.number_of_samples),
                value,
            ),
            _p("", value),
        ],
        [
            _lv("Sampling Done by Laboratory:", "", value),
            _p(_yes_no(data.sampling_by_lab), value),
        ],
        [
            _lv(
                "Storage Temperature of sample required:",
                data.storage_temperature or "",
                value,
            ),
            _p("", value),
        ],
        [
            _lv_br(
                "Specific test method/ Specification to be followed:",
                data.test_method_spec or "",
                value,
            ),
            _p("", value),
        ],
        [
            _lv("Decision Rule required:", "", value),
            _p(_yes_no(data.decision_rule), value),
        ],
        [
            _lv("Service required:", "", value),
            _p(_service_marks(data.service_type), value),
        ],
        [
            _lv("Mode of report delivery:", "", value),
            _p(_delivery_marks(data.delivery_mode), value),
        ],
        [
            _lv("Payment Details:", "", value),
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

    notes = Paragraph(
        "<b>Note:</b> "
        "1) The samples will be processed only after receiving the advance payment. "
        "2) Kindly pay entire amount if report has to be sent by courier/ email/Whatsapp. "
        "3) Samples will be stored for 7 Days after Report dispatch.",
        note_style,
    )
    note_table = Table([[notes]], colWidths=[usable])
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

    sign_table = Table(
        [
            [
                _p("Receiver's Sign & date", sign_style),
                _p("Customer Signature & date:", sign_style),
            ]
        ],
        colWidths=col_w,
    )
    story.append(sign_table)

    filled = [s for s in data.samples if not s.is_empty()]

    for index, sample in enumerate(filled, start=1):
        story.append(PageBreak())
        story.append(Paragraph(SAMPLE_SECTION_HEADING, section_style))
        story.append(_build_one_sample_table(sample, index, usable, th_style, td_style))
        story.extend(_build_tests_block(sample, td_style))

    for sample in filled:
        story.append(PageBreak())
        story.append(Paragraph(CHECKLIST_TITLE, section_style))
        story.append(_build_verification_table(sample, usable, th_style, td_style))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()


def generate_pdf_bytes(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """Build the filled Customer Test Request PDF via ReportLab."""
    return _generate_ctr_pdf(
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
