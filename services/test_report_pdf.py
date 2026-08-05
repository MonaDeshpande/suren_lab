"""
services/test_report_pdf.py
---------------------------
Customer-facing Test Report PDF (QSF No -7.8.2).

Layout mirrors reference/Test Report Format (1).pdf via ReportLab (A4).
Fills client + protocol data; leaves unavailable metadata blank.
Chemical rows = only tests selected for the sample (excl. appearance).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.branding import (
    LOGO_HEIGHT_IN,
    LOGO_PATH,
    LOGO_WIDTH_IN,
    ORGANIZATION_NAME,
    TEST_REPORT_LETTERHEAD_PT,
)
from services.protocol_store import ProtocolHeader, TestResultRow
from services.protocols.test_catalog import (
    CATEGORY_MICRO,
    CATEGORY_WATER,
    TEST_CATALOG,
    catalog_keys_for_category,
    get_test,
    normalize_category,
    uses_nutrition_template,
)
from services.samples import (
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITH_LOGO,
    SampleRecord,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
    report_keys_for_sample,
)
from services.audit import format_stamp_datetime, generator_stamp_lines

BORDER = colors.black
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

# FSSAI specs from reference Test Report Format (whole Jaggery)
FSSAI_SPECS: dict[str, str] = {
    "moisture": "Not more than 7 %",
    "acid_insoluble_ash": "Not more than 0.5 % on dry wt. basis",
    "added_color": "Shall be Absent",
    "extraneous_matter": "Not more than 2.0 % on dry wt. basis",
    "invert_sugar": "Not less than 90 % on dry wt. basis",
    "reducing_sugar": "Not more than 20 %",
    "sucrose": "Not less than 70 % on dry wt. basis",
    "sulphated_ash": "Not more than 4.0 %",
    "sulphur_dioxide": "Not more than 50 mg/kg",
    # total_ash: blank — not in reference chemical table
}

SPECS_HEADER = (
    "Specifications FSSAI 2006, Rules & Regulations, "
    "Latest Amendments Up to 12/08/2025"
)

REMARK_TEXT = (
    "Remark: The sample given for analysis confirm to the specifications of "
    "FSSAI 2006, Rules and Regulations Latest Amendments Up to 12/08/2025 as per "
    "the above tests processed. The Results are pertaining to the sample sent "
    "for analysis only. The Specifications mentioned are for whole Jaggery."
)

WATER_REMARK_TEXT = (
    "Remark: The results pertain to the water sample sent for analysis as stated "
    "above. Specifications are not listed unless provided by the customer."
)

NUTRITION_REMARK_TEXT = (
    "Remark: The results pertain to the food sample sent for analysis as stated "
    "above. Nutrition specifications are not listed unless provided by the customer."
)

WATER_SPECS_HEADER = "Specifications (as applicable)"
NUTRITION_SPECS_HEADER = "Specifications (as applicable)"

DEFAULT_TESTS_PROCESSED = "As per customer request"

DISCLAIMER_BULLETS = [
    "Sample submitted by the customer in their own container.",
    "Above analysis result is valid only for specific sample as stated above, "
    "without any bias to its source.",
    "We claim no responsibility for changes made in the report after dispatch "
    "e.g. Use of whitener or eraser.",
    "Above test report cannot be produced as legal evidence without our prior "
    "written permission.",
    "Sample stored for one week and test Report for one year from the date "
    "received. Duplicate copies of Report or Invoice will be charged extra.",
]


@dataclass
class TestReportRow:
    sr_no: int
    test_name: str
    result: str
    specification: str
    method: str


@dataclass
class TestReportData:
    """Mapped fields for one Test Report PDF."""

    customer_name_address: str = ""
    customer_sample_id: str = ""
    batch_no: str = ""
    mfg_date: str = ""
    exp_date: str = ""
    lab_code: str = ""
    date_of_sample_receipt: str = ""
    sample_name: str = ""
    sample_drawn_by: str = ""
    condition_of_sample: str = ""
    test_performance_date: str = ""
    tests_processed: str = ""
    sample_quantity: str = ""
    appearance: str = ""
    date_of_sampling: str = "--"
    sampling_done_by: str = ""
    location_of_sampling: str = "--"
    sampling_method: str = "--"
    ulr_no: str = ""
    report_date: str = ""
    report_no: str = ""
    generated_by: str = ""
    generated_at: str = ""
    rows: list[TestReportRow] = field(default_factory=list)
    remark_text: str = REMARK_TEXT
    specs_header: str = SPECS_HEADER
    is_water: bool = False
    is_nutrition: bool = False


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
    return Paragraph(_escape(text).replace("\n", "<br/>"), style)


def _report_keys(
    sample: SampleRecord,
    row_filter: Optional[set[str]] = None,
) -> list[str]:
    """Selected catalog keys in category order (food excludes appearance)."""
    chem_keys = report_keys_for_sample(sample)
    if row_filter is not None:
        chem_keys = [k for k in chem_keys if k in row_filter]
    return chem_keys


def build_test_report_data(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    report_date: Optional[date] = None,
    generated_by: str = "",
    generated_at: str = "",
    row_filter: Optional[set[str]] = None,
    condition_of_sample: str | None = None,
    tests_processed: str | None = None,
    specification_by_test_name: dict[str, str] | None = None,
) -> TestReportData:
    """Collate client + protocol into Test Report fields."""
    results_by_key = {r.test_key: r for r in results}
    cat = normalize_category(sample.category)
    is_water = cat == CATEGORY_WATER
    is_nutrition = not is_water and uses_nutrition_template(sample.selected_test_keys())
    chem_keys = _report_keys(sample, row_filter=row_filter)

    name_addr_parts = [sample.customer_name or ""]
    if (sample.customer_address or "").strip():
        name_addr_parts.append(sample.customer_address.strip())
    name_address = "\n".join(p for p in name_addr_parts if p)

    if sample.sampling_by_lab is True:
        sampling_done = "Laboratory"
    else:
        sampling_done = ""

    rows: list[TestReportRow] = []
    for i, key in enumerate(chem_keys, start=1):
        try:
            lab_test = get_test(key)
        except KeyError:
            continue
        saved = results_by_key.get(key)
        result_val = ""
        if saved and (saved.result_value or "").strip():
            result_val = saved.result_value.strip()
            if saved.unit and saved.unit not in result_val:
                result_val = f"{result_val} {saved.unit}".strip()
        method = (saved.method if saved and saved.method else lab_test.method) or ""
        if is_water or key.startswith("bn_"):
            spec = ""
        else:
            spec = FSSAI_SPECS.get(key, "")
        rows.append(
            TestReportRow(
                sr_no=i,
                test_name=lab_test.name,
                result=result_val,
                specification=spec,
                method=method,
            )
        )

    if specification_by_test_name:
        for row in rows:
            if row.test_name in specification_by_test_name:
                row.specification = specification_by_test_name[row.test_name]

    rd = report_date or date.today()
    stamp_at = (generated_at or "").strip() or format_stamp_datetime()
    if is_water:
        remark = WATER_REMARK_TEXT
        specs_hdr = WATER_SPECS_HEADER
    elif is_nutrition:
        remark = NUTRITION_REMARK_TEXT
        specs_hdr = NUTRITION_SPECS_HEADER
    else:
        remark = REMARK_TEXT
        specs_hdr = SPECS_HEADER
    return TestReportData(
        customer_name_address=name_address,
        batch_no=sample.batch_code or "",
        lab_code=sample.sample_code or sample.lab_code or "",
        date_of_sample_receipt=_fmt_date(header.sample_received_on),
        sample_name=sample.sample_name or "",
        test_performance_date=_fmt_date(header.date_of_analysis),
        condition_of_sample=(
            condition_of_sample if condition_of_sample is not None else ""
        ),
        tests_processed=(
            tests_processed
            if tests_processed is not None
            else DEFAULT_TESTS_PROCESSED
        ),
        sample_quantity=sample.quantity or "",
        appearance=(header.appearance_text or "").strip() if not is_water else "",
        sampling_done_by=sampling_done,
        report_date=_fmt_date(rd),
        generated_by=(generated_by or "").strip(),
        generated_at=stamp_at,
        rows=rows,
        remark_text=remark,
        specs_header=specs_hdr,
        is_water=is_water,
        is_nutrition=is_nutrition,
    )


def suggest_test_report_filename(sample: SampleRecord) -> str:
    """Filesystem-safe download name."""

    def _safe(text: str) -> str:
        cleaned = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text
        )
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_")

    name = _safe(sample.sample_name or "sample")[:40] or "sample"
    code = _safe(sample.sample_code or "")[:30]
    parts = ["TestReport", name]
    if code:
        parts.append(code)
    return "_".join(parts) + ".pdf"


def generate_test_report_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    report_date: Optional[date] = None,
    generated_by: str = "",
    generated_at: str = "",
    condition_of_sample: str | None = None,
    tests_processed: str | None = None,
    specification_by_test_name: dict[str, str] | None = None,
) -> bytes:
    """Build the filled Test Report PDF bytes."""
    report_kwargs = {
        "report_date": report_date,
        "generated_by": generated_by,
        "generated_at": generated_at,
        "condition_of_sample": condition_of_sample,
        "tests_processed": tests_processed,
        "specification_by_test_name": specification_by_test_name,
    }
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_BOTH:
        sections: list[tuple[TestReportData, bool]] = []
        if logo_test_keys(sample):
            sections.append(
                (
                    build_test_report_data(
                        sample,
                        header,
                        results,
                        row_filter=logo_test_keys(sample),
                        **report_kwargs,
                    ),
                    True,
                )
            )
        if no_logo_test_keys(sample):
            sections.append(
                (
                    build_test_report_data(
                        sample,
                        header,
                        results,
                        row_filter=no_logo_test_keys(sample),
                        **report_kwargs,
                    ),
                    False,
                )
            )
        if not sections:
            data = build_test_report_data(
                sample,
                header,
                results,
                **report_kwargs,
            )
            return _render_pdf(data, include_logo=True)
        return _render_pdf_sections(sections)

    include_logo = fmt == REPORT_FORMAT_WITH_LOGO
    data = build_test_report_data(
        sample,
        header,
        results,
        **report_kwargs,
    )
    return _render_pdf(data, include_logo=include_logo)


def _letterhead_story(usable: float, include_logo: bool) -> list:
    """Top letterhead band — logo or blank spacer matching reference layout."""
    story: list = []
    band = float(TEST_REPORT_LETTERHEAD_PT)
    if include_logo and LOGO_PATH.exists():
        logo_h = usable * (LOGO_HEIGHT_IN / LOGO_WIDTH_IN)
        logo = RLImage(str(LOGO_PATH), width=usable, height=logo_h)
        story.append(logo)
        pad = band - logo_h
        if pad > 2:
            story.append(Spacer(1, pad))
    else:
        story.append(Spacer(1, band))
    return story


def _render_pdf_sections(sections: list[tuple[TestReportData, bool]]) -> bytes:
    """Render one PDF with multiple report sections (e.g. logo + no-logo)."""
    if len(sections) == 1:
        return _render_pdf(sections[0][0], include_logo=sections[0][1])
    buffer = io.BytesIO()
    page_w, page_h = A4
    left = 18 * mm
    right = 18 * mm
    usable = page_w - left - right
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=8 * mm,
        bottomMargin=12 * mm,
        title="Test Report",
        author=ORGANIZATION_NAME,
    )
    styles = _report_styles()
    story: list = []
    for idx, (data, include_logo) in enumerate(sections):
        if idx > 0:
            story.append(PageBreak())
        story.extend(_build_report_story(data, styles, usable, include_logo))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawRightString(
            page_w - right,
            8 * mm,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _report_styles() -> dict:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TRTitle",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=14,
            alignment=TA_CENTER,
            leading=16,
        ),
        "qsf": ParagraphStyle(
            "TRQsf",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=9,
            alignment=TA_CENTER,
            leading=11,
        ),
        "label": ParagraphStyle(
            "TRLabel",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
        "value": ParagraphStyle(
            "TRValue",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "TRSection",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=11,
            alignment=TA_CENTER,
            leading=13,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "th": ParagraphStyle(
            "TRTh",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
        ),
        "td": ParagraphStyle(
            "TRTd",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
        ),
        "td_center": ParagraphStyle(
            "TRTdC",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "TRSmall",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
        "sign": ParagraphStyle(
            "TRSign",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
        ),
        "end": ParagraphStyle(
            "TREnd",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=9,
            alignment=TA_CENTER,
            leading=11,
        ),
    }


def _build_report_story(
    data: TestReportData,
    styles: dict,
    usable: float,
    include_logo: bool,
) -> list:
    title_style = styles["title"]
    qsf_style = styles["qsf"]
    label_style = styles["label"]
    value_style = styles["value"]
    section_style = styles["section"]
    th_style = styles["th"]
    td_style = styles["td"]
    td_center = styles["td_center"]
    small = styles["small"]
    sign_style = styles["sign"]
    end_style = styles["end"]

    story: list = []
    story.extend(_letterhead_story(usable, include_logo))

    # ----- Header bar -----
    header_tbl = Table(
        [
            [
                _p("", value_style),
                _p("TEST REPORT", title_style),
                _p("QSF No -7.8.2", qsf_style),
            ]
        ],
        colWidths=[usable * 0.28, usable * 0.44, usable * 0.28],
    )
    header_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 4))

    # ----- ULR / Date / Report No -----
    id_tbl = Table(
        [
            [_p(f"ULR No: {data.ulr_no}", small)],
            [
                _p(f"Date: {data.report_date or '--/--/----'}", small),
                _p(f"Report No: {data.report_no or '---/26/---/--/--'}", small),
            ],
        ],
        colWidths=[usable * 0.5, usable * 0.5],
    )
    id_tbl.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("ALIGN", (1, 1), (1, 1), "RIGHT"),
            ]
        )
    )
    story.append(id_tbl)
    story.append(Spacer(1, 4))

    # ----- Sample / customer info (label | value | label | value) -----
    lw = usable * 0.22
    vw = usable * 0.28

    def _pair(l1: str, v1: str, l2: str, v2: str) -> list:
        return [
            _p(l1, label_style),
            _p(v1, value_style),
            _p(l2, label_style),
            _p(v2, value_style),
        ]

    info_rows = [
        [
            _p("Customer Name & Address", label_style),
            _p(data.customer_name_address, value_style),
            _p("", value_style),
            _p("", value_style),
        ],
        _pair(
            "Customer Sample ID",
            data.customer_sample_id,
            "Batch No.",
            data.batch_no,
        ),
        _pair("Mfg Date", data.mfg_date, "Exp Date", data.exp_date),
        _pair(
            "Lab Code",
            data.lab_code,
            "Date of Sample Receipt",
            data.date_of_sample_receipt,
        ),
        _pair(
            "Sample Name",
            data.sample_name,
            "Sample Drawn By",
            data.sample_drawn_by,
        ),
        _pair(
            "Condition Of Sample",
            data.condition_of_sample,
            "Test Performance Date",
            data.test_performance_date,
        ),
        _pair(
            "Tests processed",
            data.tests_processed,
            "Sample quantity",
            data.sample_quantity,
        ),
        [
            _p("Appearance", label_style),
            _p(data.appearance, value_style),
            _p("", value_style),
            _p("", value_style),
        ],
        _pair(
            "Date of Sampling",
            data.date_of_sampling,
            "Sampling Done by",
            data.sampling_done_by,
        ),
        _pair(
            "Location of sampling",
            data.location_of_sampling,
            "Sampling Method",
            data.sampling_method,
        ),
    ]

    info_tbl = Table(info_rows, colWidths=[lw, vw, lw, vw])
    info_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("SPAN", (1, 0), (3, 0)),  # customer name/address
                ("SPAN", (1, 7), (3, 7)),  # appearance
            ]
        )
    )
    story.append(info_tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph("CHEMICAL TEST REPORT", section_style))

    # ----- Results table -----
    col_sr = 12 * mm
    col_name = usable * 0.28
    col_result = usable * 0.12
    col_spec = usable * 0.28
    col_method = usable - col_sr - col_name - col_result - col_spec

    result_header = [
        _p("Sr. No", th_style),
        _p("Name of Test", th_style),
        _p("Result", th_style),
        _p(data.specs_header, th_style),
        _p("Method of Analysis", th_style),
    ]
    body = [result_header]
    for row in data.rows:
        body.append(
            [
                _p(str(row.sr_no), td_center),
                _p(row.test_name, td_style),
                _p(row.result, td_center),
                _p(row.specification, td_style),
                _p(row.method, td_style),
            ]
        )

    # Remark as final merged row
    body.append(
        [
            _p(data.remark_text, small),
            _p("", small),
            _p("", small),
            _p("", small),
            _p("", small),
        ]
    )

    results_tbl = Table(
        body,
        colWidths=[col_sr, col_name, col_result, col_spec, col_method],
        repeatRows=1,
    )
    last = len(body) - 1
    results_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, last - 1), 0.5, BORDER),
                ("LINEBELOW", (0, last - 1), (-1, last - 1), 0.5, BORDER),
                ("BOX", (0, last), (-1, last), 1, BORDER),
                ("SPAN", (0, last), (-1, last)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(results_tbl)
    story.append(Spacer(1, 14))

    # ----- Signature block -----
    # Left (authorized signatory) and Checked by left blank for pen at client
    sign_left = (
        "________________________<br/>"
        "<br/>"
        "<br/>"
        f"For, {ORGANIZATION_NAME}"
    )
    sign_tbl = Table(
        [
            [
                Paragraph(sign_left, sign_style),
                _p("Checked by:\n\n________________________", sign_style),
            ]
        ],
        colWidths=[usable * 0.5, usable * 0.5],
    )
    sign_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(sign_tbl)
    story.append(Spacer(1, 12))

    # ----- Disclaimer -----
    story.append(_p("Disclaimer", label_style))
    for bullet in DISCLAIMER_BULLETS:
        story.append(_p(f"• {bullet}", small))
    story.append(Spacer(1, 10))

    # ----- Generator stamp (who printed this report) -----
    for line in generator_stamp_lines(data.generated_by, data.generated_at):
        story.append(_p(line, small))
    story.append(Spacer(1, 6))
    story.append(Paragraph("End of Report", end_style))
    return story


def _render_pdf(data: TestReportData, *, include_logo: bool = True) -> bytes:
    buffer = io.BytesIO()
    page_w, _page_h = A4
    left = 18 * mm
    right = 18 * mm
    usable = page_w - left - right
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=8 * mm,
        bottomMargin=12 * mm,
        title="Test Report",
        author=ORGANIZATION_NAME,
    )
    styles = _report_styles()
    story = _build_report_story(data, styles, usable, include_logo)

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawRightString(page_w - right, 8 * mm, "Page 1 of 1")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


@dataclass
class FinalReportOutput:
    """Generated final report artifacts (food = PDF; water/micro = DOCX + optional PDF)."""

    docx_bytes: bytes | None = None
    pdf_bytes: bytes | None = None
    docx_filename: str = ""
    pdf_filename: str = ""
    is_water: bool = False
    is_micro: bool = False


def generate_final_report(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    report_date: Optional[date] = None,
    generated_by: str = "",
    generated_at: str = "",
    condition_of_sample: str | None = None,
    tests_processed: str | None = None,
    specification_by_test_name: dict[str, str] | None = None,
    *,
    water_opts: object | None = None,
    micro_opts: object | None = None,
) -> FinalReportOutput:
    """
    Route final report generation by sample category.

    Food samples use ReportLab PDF. Water and Micro samples use Word fillers.
    """
    cat = normalize_category(sample.category)
    if cat == CATEGORY_WATER:
        from services.test_report_water_docx import (
            WaterReportFillOptions,
            generate_water_test_report_pdf_bytes,
            suggest_water_test_report_filename,
        )

        opts = (
            water_opts
            if isinstance(water_opts, WaterReportFillOptions)
            else WaterReportFillOptions()
        )
        if generated_by:
            opts.generated_by = generated_by
        if generated_at:
            opts.generated_at = generated_at
        if condition_of_sample is not None:
            opts.condition_of_sample = condition_of_sample
        if report_date is not None:
            opts.report_date = report_date
        docx_bytes, pdf_bytes = generate_water_test_report_pdf_bytes(
            sample, header, results, opts=opts
        )
        return FinalReportOutput(
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
            docx_filename=suggest_water_test_report_filename(sample, extension="docx"),
            pdf_filename=suggest_water_test_report_filename(sample, extension="pdf"),
            is_water=True,
        )

    if cat == CATEGORY_MICRO:
        from services.test_report_micro_docx import (
            MicroReportFillOptions,
            generate_micro_test_report_pdf_bytes,
            suggest_micro_test_report_filename,
        )

        opts = (
            micro_opts
            if isinstance(micro_opts, MicroReportFillOptions)
            else MicroReportFillOptions()
        )
        if generated_by:
            opts.generated_by = generated_by
        if generated_at:
            opts.generated_at = generated_at
        if condition_of_sample is not None:
            opts.condition_of_sample = condition_of_sample
        if report_date is not None:
            opts.report_date = report_date
        docx_bytes, pdf_bytes = generate_micro_test_report_pdf_bytes(
            sample, header, results, opts=opts
        )
        return FinalReportOutput(
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
            docx_filename=suggest_micro_test_report_filename(sample, extension="docx"),
            pdf_filename=suggest_micro_test_report_filename(sample, extension="pdf"),
            is_micro=True,
        )

    pdf_bytes = generate_test_report_pdf_bytes(
        sample,
        header,
        results,
        report_date=report_date,
        generated_by=generated_by,
        generated_at=generated_at,
        condition_of_sample=condition_of_sample,
        tests_processed=tests_processed,
        specification_by_test_name=specification_by_test_name,
    )
    return FinalReportOutput(
        pdf_bytes=pdf_bytes,
        pdf_filename=suggest_test_report_filename(sample),
        is_water=False,
    )
