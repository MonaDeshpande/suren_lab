"""
services/test_report_water_docx.py
----------------------------------
Fill reference/Water test report.docx for water sample final reports.

Layout matches the reference multi-section Word document (Chemical + Elemental,
Physical, Microbiological placeholder). PDF conversion reuses docx2pdf when available.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document

from services.audit import format_stamp_datetime, generator_stamp_lines
from services.docx_to_pdf import try_convert_docx_to_pdf
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord, water_report_keys
from services.water_report_catalog import (
    DEFAULT_TESTING_CONDUCTED_AT,
    WATER_MICRO_PLACEHOLDERS,
    WATER_REPORT_CHEMICAL_TABLE_ROWS,
    WATER_REPORT_ELEMENTAL_TABLE_ROWS,
    WATER_REPORT_LIMITS,
    WATER_REPORT_METHOD_LABELS,
    WATER_REPORT_PHYSICAL_TABLE_ROWS,
    WATER_REPORT_REMARK_CHEMICAL,
    WATER_REPORT_REMARK_MICRO,
    WaterReportLimits,
    limits_for_key,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WATER_REPORT_TEMPLATE_PATH = PROJECT_ROOT / "reference" / "Water test report.docx"

DEFAULT_CUSTOMER_SAMPLE_ID = "Drinking Water"
BLANK_FIELD = "---"


@dataclass
class WaterReportFillOptions:
    """Reviewer-editable fields for water final report."""

    ulr_no: str = ""
    report_no_chemical: str = ""
    report_no_micro: str = ""
    report_date: Optional[date] = None
    condition_of_sample: str = ""
    customer_sample_id: str = ""
    date_of_sampling: str = BLANK_FIELD
    location_of_sampling: str = BLANK_FIELD
    sampling_method: str = BLANK_FIELD
    sampling_done_by: str = BLANK_FIELD
    sample_appearance: str = ""
    testing_conducted_at: str = DEFAULT_TESTING_CONDUCTED_AT
    test_performance_date: str = ""
    limit_overrides: dict[str, WaterReportLimits] = field(default_factory=dict)
    generated_by: str = ""
    generated_at: str = ""


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


def _set_cell(cell, text: str) -> None:
    text = text or ""
    paragraphs = cell.paragraphs
    if not paragraphs:
        cell.text = text
        return
    paragraphs[0].text = text
    for p in paragraphs[1:]:
        p.text = ""


def _set_paragraph_text(paragraph, text: str) -> None:
    paragraph.text = text or ""


def _blank_signatory_paragraphs(doc: Document) -> None:
    """Remove hardcoded signatory names; leave blocks for pen signature."""
    signatory_markers = ("Mrs.", "Dr.", "Quality Manager", "Director")
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if any(marker in text for marker in signatory_markers):
            if "Disclaimer" in text or "Remark" in text:
                continue
            if text.startswith("For "):
                continue
            _set_paragraph_text(para, "")


def _result_display(res: TestResultRow) -> str:
    val = (res.result_value or "").strip()
    if not val:
        return ""
    unit = (res.unit or "").strip()
    if unit and unit not in val and unit != "—":
        return f"{val} {unit}"
    return val


def _default_report_numbers(sample: SampleRecord) -> tuple[str, str]:
    base = (sample.lab_code or sample.sample_code or "").strip().rstrip("/")
    if not base:
        return "", ""
    return f"{base}/01", f"{base}/02"


def _fill_customer_info_table(
    table,
    sample: SampleRecord,
    header: ProtocolHeader,
    opts: WaterReportFillOptions,
) -> None:
    if len(table.rows) < 9:
        return

    name_addr_parts = [sample.customer_name or ""]
    if (sample.customer_address or "").strip():
        name_addr_parts.append(sample.customer_address.strip())
    name_address = "\n".join(p for p in name_addr_parts if p)

    customer_sample_id = (
        opts.customer_sample_id
        or (sample.parameters or "").strip()
        or DEFAULT_CUSTOMER_SAMPLE_ID
    )
    appearance = opts.sample_appearance or (header.appearance_text or "").strip()
    perf_date = opts.test_performance_date or _fmt_date(header.date_of_analysis)
    testing_at = opts.testing_conducted_at or DEFAULT_TESTING_CONDUCTED_AT

    _set_cell(table.rows[0].cells[1], name_address)
    _set_cell(table.rows[1].cells[1], customer_sample_id)
    _set_cell(table.rows[1].cells[3], sample.batch_code or BLANK_FIELD)
    _set_cell(table.rows[2].cells[1], sample.lab_code or sample.sample_code or "")
    _set_cell(table.rows[2].cells[3], opts.date_of_sampling or BLANK_FIELD)
    _set_cell(table.rows[3].cells[1], _fmt_date(header.sample_received_on))
    _set_cell(table.rows[3].cells[3], opts.location_of_sampling or BLANK_FIELD)
    _set_cell(table.rows[4].cells[1], sample.sample_name or "")
    _set_cell(table.rows[5].cells[1], opts.sampling_method or BLANK_FIELD)
    _set_cell(table.rows[5].cells[3], opts.sampling_done_by or BLANK_FIELD)
    _set_cell(
        table.rows[6].cells[1],
        opts.condition_of_sample or "",
    )
    _set_cell(table.rows[6].cells[3], perf_date)
    _set_cell(table.rows[7].cells[1], appearance)
    _set_cell(table.rows[7].cells[3], sample.quantity or "")
    _set_cell(table.rows[8].cells[1], testing_at)


def _fill_result_row(
    table,
    row_idx: int,
    test_key: str,
    by_key: dict[str, TestResultRow],
    limit_overrides: dict[str, WaterReportLimits],
) -> None:
    if row_idx >= len(table.rows):
        return
    row = table.rows[row_idx]
    if len(row.cells) < 6:
        return
    limits = limits_for_key(test_key, limit_overrides)
    res = by_key.get(test_key)
    result_text = _result_display(res) if res else ""
    _set_cell(row.cells[2], result_text)
    if limits.desirable:
        _set_cell(row.cells[3], limits.desirable)
    if limits.permissible:
        _set_cell(row.cells[4], limits.permissible)
    method = WATER_REPORT_METHOD_LABELS.get(test_key, "")
    if method:
        _set_cell(row.cells[5], method)


def _fill_chemical_elemental_table(
    table,
    by_key: dict[str, TestResultRow],
    limit_overrides: dict[str, WaterReportLimits],
) -> None:
    for row_idx, test_key in WATER_REPORT_CHEMICAL_TABLE_ROWS.items():
        _fill_result_row(table, row_idx, test_key, by_key, limit_overrides)
    for row_idx, test_key in WATER_REPORT_ELEMENTAL_TABLE_ROWS.items():
        _fill_result_row(table, row_idx, test_key, by_key, limit_overrides)
    if len(table.rows) > 12:
        _set_cell(table.rows[12].cells[0], WATER_REPORT_REMARK_CHEMICAL)


def _fill_physical_table(
    table,
    by_key: dict[str, TestResultRow],
    limit_overrides: dict[str, WaterReportLimits],
) -> None:
    for row_idx, test_key in WATER_REPORT_PHYSICAL_TABLE_ROWS.items():
        _fill_result_row(table, row_idx, test_key, by_key, limit_overrides)


def _fill_micro_placeholder_table(table) -> None:
    """Keep micro structure; leave Result column blank until micro protocol exists."""
    if len(table.rows) < 4:
        return
    for i, placeholder in enumerate(WATER_MICRO_PLACEHOLDERS):
        row_idx = 2 + i
        if row_idx >= len(table.rows):
            break
        row = table.rows[row_idx]
        if len(row.cells) < 6:
            continue
        _set_cell(row.cells[0], placeholder.sr_no)
        _set_cell(row.cells[1], placeholder.name)
        _set_cell(row.cells[2], "")  # blank result — micro protocol pending
        _set_cell(row.cells[3], placeholder.desirable)
        if placeholder.permissible:
            _set_cell(row.cells[4], placeholder.permissible)
        _set_cell(row.cells[5], placeholder.method)
    if len(table.rows) > 4:
        _set_cell(table.rows[4].cells[0], WATER_REPORT_REMARK_MICRO)


def _fill_header_paragraphs(doc: Document, opts: WaterReportFillOptions) -> None:
    report_date = _fmt_date(opts.report_date) if opts.report_date else ""
    ulr = (opts.ulr_no or "").strip()
    chem_report = (opts.report_no_chemical or "").strip()
    micro_report = (opts.report_no_micro or "").strip()

    for i, para in enumerate(doc.paragraphs):
        text = (para.text or "").strip()
        if i == 0 and text.startswith("ULR No:"):
            _set_paragraph_text(para, f"ULR No: {ulr}" if ulr else "ULR No:")
        elif i == 2 and text.startswith("Date:"):
            _set_paragraph_text(para, f"Date: {report_date}" if report_date else "Date:")
        elif i == 3 and "Report No:" in text:
            _set_paragraph_text(
                para,
                f"Report No:  {chem_report}" if chem_report else "Report No:",
            )
        elif i == 29 and "Report No:" in text:
            date_part = f"Date: {report_date}" if report_date else "Date:"
            report_part = f"Report No: {micro_report}" if micro_report else "Report No:"
            _set_paragraph_text(para, f"{date_part}\t\t\t\t                       {report_part}")


def fill_water_test_report_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    opts: Optional[WaterReportFillOptions] = None,
) -> bytes:
    """Produce a filled water test report .docx."""
    if not WATER_REPORT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Water test report template missing: {WATER_REPORT_TEMPLATE_PATH}"
        )

    fill_opts = opts or WaterReportFillOptions()
    by_key = {r.test_key: r for r in results}

    if not fill_opts.report_no_chemical or not fill_opts.report_no_micro:
        default_chem, default_micro = _default_report_numbers(sample)
        if not fill_opts.report_no_chemical:
            fill_opts.report_no_chemical = default_chem
        if not fill_opts.report_no_micro:
            fill_opts.report_no_micro = default_micro

    if not fill_opts.report_date:
        fill_opts.report_date = header.date_of_analysis or date.today()

    if not fill_opts.sample_appearance:
        fill_opts.sample_appearance = (header.appearance_text or "").strip()

    doc = Document(io.BytesIO(WATER_REPORT_TEMPLATE_PATH.read_bytes()))
    _blank_signatory_paragraphs(doc)
    _fill_header_paragraphs(doc, fill_opts)

    tables = doc.tables
    if len(tables) >= 1:
        _fill_customer_info_table(tables[0], sample, header, fill_opts)
    if len(tables) >= 2:
        _fill_chemical_elemental_table(
            tables[1], by_key, fill_opts.limit_overrides
        )
    if len(tables) >= 3:
        _fill_customer_info_table(tables[2], sample, header, fill_opts)
    if len(tables) >= 4:
        _fill_physical_table(tables[3], by_key, fill_opts.limit_overrides)
    if len(tables) >= 5:
        _fill_micro_placeholder_table(tables[4])

    stamp_at = (fill_opts.generated_at or "").strip() or format_stamp_datetime()
    doc.add_paragraph("")
    for line in generator_stamp_lines(fill_opts.generated_by, stamp_at):
        doc.add_paragraph(line)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def suggest_water_test_report_filename(
    sample: SampleRecord,
    *,
    extension: str = "docx",
) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (sample.sample_name or sample.sample_code or "sample")
    )
    ext = extension.lstrip(".")
    return f"TestReport_{safe}_{sample.sample_code}.{ext}"


def generate_water_test_report_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    opts: Optional[WaterReportFillOptions] = None,
) -> tuple[bytes, bytes | None]:
    """
    Returns (docx_bytes, pdf_bytes_or_none).
    PDF is None when Word / LibreOffice conversion is unavailable.
    """
    docx_bytes = fill_water_test_report_docx_bytes(
        sample, header, results, opts=opts
    )
    pdf_bytes = try_convert_docx_to_pdf(docx_bytes)
    return docx_bytes, pdf_bytes


def build_water_report_limit_rows(
    sample: SampleRecord,
    results: list[TestResultRow],
    limit_overrides: Optional[dict[str, WaterReportLimits]] = None,
) -> list[dict[str, str]]:
    """Preview rows for Reviewer spec editor (Desirable / Permissible columns)."""
    by_key = {r.test_key: r for r in results}
    overrides = limit_overrides or {}
    rows: list[dict[str, str]] = []
    for key in water_report_keys(sample):
        limits = limits_for_key(key, overrides)
        res = by_key.get(key)
        result_val = _result_display(res) if res else ""
        rows.append(
            {
                "Test": key,
                "Result": result_val,
                "Desirable Limit": limits.desirable,
                "Permissible limit": limits.permissible,
                "Method": WATER_REPORT_METHOD_LABELS.get(key, ""),
            }
        )
    return rows
