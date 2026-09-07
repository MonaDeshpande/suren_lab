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
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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
    LAB_SHORT_NAME,
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
    PROTOCOL_FAMILY_JAGGERY,
    TEST_CATALOG,
    catalog_keys_for_category,
    get_test,
    normalize_category,
    protocol_family_for_key,
    uses_nutrition_template,
)
from services.test_packages import (
    is_fssai_package_type,
    is_nutrition_package_type,
    normalize_package_type,
)
from services.samples import (
    REPORT_FORMAT_BOTH,
    REPORT_FORMAT_WITH_LOGO,
    SampleRecord,
    default_report_with_logo,
    default_test_report_no,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
    report_keys_for_sample,
    report_page_label,
)
from services.audit import format_stamp_datetime
from services.ulr import generate_ulr_no, lab_code_for_ulr

BORDER = colors.black
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
_FONTS_REGISTERED = False


def _register_report_fonts() -> None:
    """Load Cambria when available; fall back to Times on other hosts."""
    global FONT, FONT_BOLD, _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    _FONTS_REGISTERED = True
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        Path(windir) / "Fonts" / "cambria.ttc",
        Path(windir) / "Fonts" / "cambriab.ttf",
        Path(windir) / "Fonts" / "Cambria.ttf",
        Path(windir) / "Fonts" / "Cambria Bold.ttf",
    ]
    regular = next((p for p in candidates if p.exists()), None)
    bold = Path(windir) / "Fonts" / "cambriab.ttf"
    if regular:
        try:
            pdfmetrics.registerFont(TTFont("Cambria", str(regular), subfontIndex=0))
            FONT = "Cambria"
        except Exception:
            FONT = "Times-Roman"
    else:
        FONT = "Times-Roman"
    if bold.exists():
        try:
            pdfmetrics.registerFont(TTFont("Cambria-Bold", str(bold)))
            FONT_BOLD = "Cambria-Bold"
        except Exception:
            FONT_BOLD = "Times-Bold"
    else:
        FONT_BOLD = "Times-Bold"

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
    "Sample stored for one week and test Report for one year from the date received.",
    "Duplicate copies of Report or Invoice will be charged extra.",
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
    authorized_signatory: str = ""
    checked_by: str = ""
    authorized_signatory_role: str = ""
    checked_by_role: str = ""
    disclaimer_bullets: list[str] = field(default_factory=list)


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


def _remark_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    """Render remark with bold label in the Name-of-Test column (reference layout)."""
    body = (text or "").strip()
    if body.lower().startswith("remark:"):
        body = body[7:].lstrip()
    html = f"<b>Remark:</b> {_escape(body)}"
    return Paragraph(html.replace("\n", "<br/>"), style)


def _uses_nutrition_report(sample: SampleRecord) -> bool:
    """
    Basic Nutrition report template when package group is Basic or Detailed Nutrition.

    Falls back to legacy bn_* key detection when package_type is missing on old rows.
    """
    ptype = normalize_package_type(getattr(sample, "package_type", None) or "")
    if ptype:
        return is_nutrition_package_type(ptype)
    return uses_nutrition_template(sample.selected_test_keys())


def _filter_fssai_report_keys(
    chem_keys: list[str],
    sample: SampleRecord,
) -> list[str]:
    """On FSSAI packages, exclude stray Basic Nutrition catalog keys from the report."""
    ptype = normalize_package_type(getattr(sample, "package_type", None) or "")
    if not is_fssai_package_type(ptype):
        return chem_keys
    return [
        key
        for key in chem_keys
        if protocol_family_for_key(key) == PROTOCOL_FAMILY_JAGGERY
    ]


def _report_keys(
    sample: SampleRecord,
    row_filter: Optional[set[str]] = None,
) -> list[str]:
    """Selected catalog keys in category order (food excludes appearance)."""
    chem_keys = report_keys_for_sample(sample)
    if row_filter is not None:
        chem_keys = [k for k in chem_keys if k in row_filter]
    return chem_keys


def default_checked_by_analysts(sample: SampleRecord) -> str:
    """Full name(s) of assigned analyst(s) for the final report Checked by block."""
    cat = normalize_category(sample.category)
    if cat == CATEGORY_WATER:
        names: list[str] = []
        if (sample.assigned_analyst_name or "").strip():
            names.append(sample.assigned_analyst_name.strip())
        if (sample.assigned_micro_analyst_name or "").strip():
            micro = sample.assigned_micro_analyst_name.strip()
            if micro not in names:
                names.append(micro)
        return "\n".join(names)
    if cat == CATEGORY_MICRO:
        return (sample.assigned_micro_analyst_name or "").strip()
    return (sample.assigned_analyst_name or "").strip()


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
    with_logo: bool | None = None,
    ulr_no: str | None = None,
    location_of_sampling: str | None = None,
    sampling_method: str | None = None,
    authorized_signatory: str | None = None,
    checked_by: str | None = None,
    remark_text: str | None = None,
    disclaimer_bullets: list[str] | None = None,
) -> TestReportData:
    """Collate client + protocol into Test Report fields."""
    results_by_key = {r.test_key: r for r in results}
    cat = normalize_category(sample.category)
    is_water = cat == CATEGORY_WATER
    is_nutrition = not is_water and _uses_nutrition_report(sample)
    chem_keys = _filter_fssai_report_keys(
        _report_keys(sample, row_filter=row_filter),
        sample,
    )

    name_addr_parts = [sample.customer_name or ""]
    if (sample.customer_address or "").strip():
        name_addr_parts.append(sample.customer_address.strip())
    name_address = "\n".join(p for p in name_addr_parts if p)

    if sample.sampling_by_lab is True:
        sampling_done = "Laboratory"
    else:
        sampling_done = "Customer"

    loc_sampling = (
        location_of_sampling
        if location_of_sampling is not None
        else "--"
    )
    samp_method = sampling_method if sampling_method is not None else "--"
    if sample.sampling_by_lab is True and samp_method == "--":
        samp_method = "Laboratory sampling"

    rows: list[TestReportRow] = []
    for i, key in enumerate(chem_keys, start=1):
        try:
            lab_test = get_test(key)
        except KeyError:
            continue
        saved = results_by_key.get(key)
        result_val = ""
        if saved and (saved.result_value or "").strip():
            from services.number_format import format_report_number

            result_val = format_report_number(saved.result_value.strip())
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
    logo_flag = default_report_with_logo(sample) if with_logo is None else with_logo
    report_no = default_test_report_no(sample, with_logo=logo_flag)
    if is_water:
        remark = WATER_REMARK_TEXT
        specs_hdr = WATER_SPECS_HEADER
    elif is_nutrition:
        remark = NUTRITION_REMARK_TEXT
        specs_hdr = NUTRITION_SPECS_HEADER
    else:
        remark = REMARK_TEXT
        specs_hdr = SPECS_HEADER
    ulr = (ulr_no or "").strip()
    if not ulr:
        ulr = generate_ulr_no(
            lab_code_for_ulr(sample.lab_code, sample.sample_code)
        )
    from services.report_settings import (
        default_authorized_signatory,
        load_report_settings,
        signatory_role,
    )

    settings = load_report_settings()
    auth_name = (authorized_signatory or "").strip() or default_authorized_signatory(
        settings
    )
    check_name = (checked_by or "").strip() or default_checked_by_analysts(sample)
    auth_role = signatory_role(auth_name, settings) or "Director"
    check_role = "Analyst" if check_name else "Quality Manager"
    bullets = (
        list(disclaimer_bullets)
        if disclaimer_bullets
        else list(settings.disclaimer_bullets or DISCLAIMER_BULLETS)
    )
    if (remark_text or "").strip():
        final_remark = remark_text.strip()
    elif not is_water and not is_nutrition:
        final_remark = settings.default_remark_text or remark
    else:
        final_remark = remark
    return TestReportData(
        customer_name_address=name_address,
        customer_sample_id=(sample.parameters or "").strip() or (sample.sample_name or ""),
        batch_no=sample.batch_code or "",
        lab_code=sample.sample_code or sample.lab_code or "",
        date_of_sample_receipt=_fmt_date(header.sample_received_on),
        sample_name=sample.sample_name or "",
        sample_drawn_by=sampling_done,
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
        location_of_sampling=loc_sampling,
        sampling_method=samp_method,
        ulr_no=ulr,
        report_date=_fmt_date(rd),
        report_no=report_no,
        generated_by=(generated_by or "").strip(),
        generated_at=stamp_at,
        rows=rows,
        remark_text=final_remark,
        specs_header=specs_hdr,
        is_water=is_water,
        is_nutrition=is_nutrition,
        authorized_signatory=auth_name,
        checked_by=check_name,
        authorized_signatory_role=auth_role,
        checked_by_role=check_role,
        disclaimer_bullets=bullets,
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
    ulr_no: str | None = None,
) -> bytes:
    """Build the filled Test Report PDF bytes."""
    report_kwargs = {
        "report_date": report_date,
        "generated_by": generated_by,
        "generated_at": generated_at,
        "condition_of_sample": condition_of_sample,
        "tests_processed": tests_processed,
        "specification_by_test_name": specification_by_test_name,
        "ulr_no": ulr_no,
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
                        with_logo=True,
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
                        with_logo=False,
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
        n = canvas.getPageNumber()
        include_logo = sections[min(n - 1, len(sections) - 1)][1]
        canvas.drawRightString(
            page_w - right,
            8 * mm,
            report_page_label(with_logo=include_logo),
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _report_styles() -> dict:
    _register_report_fonts()
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TRTitle",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=16,
            alignment=TA_CENTER,
            leading=18,
        ),
        "qsf": ParagraphStyle(
            "TRQsf",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=10,
            alignment=TA_CENTER,
            leading=12,
        ),
        "label": ParagraphStyle(
            "TRLabel",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
        ),
        "value": ParagraphStyle(
            "TRValue",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "TRSection",
            parent=styles["Normal"],
            fontName=FONT_BOLD,
            fontSize=14,
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
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
        ),
        "td_center": ParagraphStyle(
            "TRTdC",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
        ),
        "remark": ParagraphStyle(
            "TRRemark",
            parent=styles["Normal"],
            fontName=FONT,
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
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
            fontSize=10,
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
    remark_style = styles["remark"]
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
    if include_logo:
        id_rows = [
            [_p(f"ULR No: {data.ulr_no}", small)],
            [
                _p(f"Date: {data.report_date or '--/--/----'}", small),
                _p(f"Report No: {data.report_no or '---/26/---/--/--'}", small),
            ],
        ]
        id_style = [
            ("SPAN", (0, 0), (1, 0)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("ALIGN", (1, 1), (1, 1), "RIGHT"),
        ]
    else:
        id_rows = [
            [
                _p(f"Date: {data.report_date or '--/--/----'}", small),
                _p(f"Report No: {data.report_no or '---/26/---/--/--'}", small),
            ],
        ]
        id_style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]
    id_tbl = Table(id_rows, colWidths=[usable * 0.5, usable * 0.5])
    id_tbl.setStyle(TableStyle(id_style))
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

    # Remark as final merged row (empty Sr. No; text starts in Name of Test column)
    body.append(
        [
            _p("", td_style),
            _remark_paragraph(data.remark_text, remark_style),
            _p("", td_style),
            _p("", td_style),
            _p("", td_style),
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
                ("SPAN", (1, last), (-1, last)),
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
    auth = (data.authorized_signatory or "xxx").strip()
    checked = (data.checked_by or "").strip()
    auth_role = (data.authorized_signatory_role or "Director").strip()
    checked_role = (data.checked_by_role or "Quality Manager").strip()
    sign_left = (
        f"{auth}<br/>"
        f"{auth_role}<br/>"
        "Authorized signatory<br/>"
        f"For, {LAB_SHORT_NAME}"
    )
    sign_right = (
        f"{checked}<br/>"
        f"{checked_role}<br/>"
        "Authorized Signatory<br/>"
        f"For {LAB_SHORT_NAME}"
        if checked
        else "Checked by:"
    )
    sign_tbl = Table(
        [
            [
                Paragraph(sign_left, sign_style),
                Paragraph(sign_right, sign_style),
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
    bullets = data.disclaimer_bullets or DISCLAIMER_BULLETS
    for bullet in bullets:
        story.append(_p(f"• {bullet}", small))
    story.append(Spacer(1, 10))

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
        canvas.drawRightString(
            page_w - right,
            8 * mm,
            report_page_label(with_logo=include_logo),
        )
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
    ulr_no: str | None = None,
    location_of_sampling: str | None = None,
    sampling_method: str | None = None,
    authorized_signatory: str | None = None,
    checked_by: str | None = None,
    remark_text: str | None = None,
    disclaimer_bullets: list[str] | None = None,
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

    # Food — Word template matching reference/Test Report Format (1).pdf
    from services.test_report_food_docx import (
        generate_food_test_report_pdf_bytes,
        suggest_food_test_report_docx_filename,
    )

    docx_bytes, pdf_bytes = generate_food_test_report_pdf_bytes(
        sample,
        header,
        results,
        report_date=report_date,
        generated_by=generated_by,
        generated_at=generated_at,
        condition_of_sample=condition_of_sample,
        tests_processed=tests_processed,
        specification_by_test_name=specification_by_test_name,
        ulr_no=ulr_no,
        location_of_sampling=location_of_sampling,
        sampling_method=sampling_method,
        authorized_signatory=authorized_signatory,
        checked_by=checked_by,
        remark_text=remark_text,
        disclaimer_bullets=disclaimer_bullets,
    )
    pdf_name = suggest_test_report_filename(sample)
    return FinalReportOutput(
        docx_bytes=docx_bytes,
        pdf_bytes=pdf_bytes or generate_test_report_pdf_bytes(
            sample,
            header,
            results,
            report_date=report_date,
            generated_by=generated_by,
            generated_at=generated_at,
            condition_of_sample=condition_of_sample,
            tests_processed=tests_processed,
            specification_by_test_name=specification_by_test_name,
            ulr_no=ulr_no,
        ),
        docx_filename=suggest_food_test_report_docx_filename(sample),
        pdf_filename=pdf_name,
        is_water=False,
    )
