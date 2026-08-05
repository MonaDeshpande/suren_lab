"""
services/test_report_micro_docx.py
----------------------------------
Build Micro final test report matching reference/Micro Test Report.htm.

Layout: QSF header, Date/Report No, customer metadata table, results table
under "Microbiological Test" (Sr / Name / Result / Limits / Method), disclaimer.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from services.audit import format_stamp_datetime, generator_stamp_lines
from services.docx_to_pdf import try_convert_docx_to_pdf
from services.micro_report_catalog import (
    MICRO_DISCLAIMER_LINES,
    MICRO_END_OF_REPORT,
    MICRO_REPORT_QSF,
    MICRO_REPORT_SECTION_TITLE,
    micro_report_keys_ordered,
    spec_for_key,
)
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord

logger = logging.getLogger(__name__)

BLANK_FIELD = "--"


@dataclass
class MicroReportFillOptions:
    """Reviewer-editable fields for micro final report."""

    report_no: str = ""
    report_date: Optional[date] = None
    condition_of_sample: str = ""
    customer_sample_id: str = ""
    date_of_sampling: str = BLANK_FIELD
    location_of_sampling: str = BLANK_FIELD
    sampling_method: str = BLANK_FIELD
    sample_appearance: str = ""
    test_performance_date: str = ""
    generated_by: str = ""
    generated_at: str = ""


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return ""
    return d.strftime("%d-%m-%Y")


def _set_run_font(run, *, size_pt: float = 10, bold: bool = False) -> None:
    run.font.name = "Cambria"
    run.font.size = Pt(size_pt)
    run.bold = bold


def _add_centered(doc: Document, text: str, *, size_pt: float = 12, bold: bool = True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    _set_run_font(run, size_pt=size_pt, bold=bold)
    return p


def _add_right(doc: Document, text: str, *, size_pt: float = 10):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    _set_run_font(run, size_pt=size_pt)
    return p


def _set_cell_text(cell, text: str, *, size_pt: float = 10, bold: bool = False) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text or "")
    _set_run_font(run, size_pt=size_pt, bold=bold)


def _sampling_done_by_lab(sample: SampleRecord) -> str:
    if sample.sampling_by_lab is True:
        return "Yes"
    if sample.sampling_by_lab is False:
        return "No"
    return BLANK_FIELD


def _sample_drawn_by(sample: SampleRecord) -> str:
    if sample.sampling_by_lab is True:
        return "Laboratory"
    if sample.sampling_by_lab is False:
        return "Customer"
    return BLANK_FIELD


def _default_report_no(sample: SampleRecord) -> str:
    base = (sample.lab_code or sample.sample_code or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/01"


def _result_display(res: Optional[TestResultRow]) -> str:
    if res is None:
        return ""
    return (res.result_value or "").strip()


def _fill_metadata_table(
    table,
    sample: SampleRecord,
    header: ProtocolHeader,
    opts: MicroReportFillOptions,
) -> None:
    name_addr_parts = [sample.customer_name or ""]
    if (sample.customer_address or "").strip():
        name_addr_parts.append(sample.customer_address.strip())
    name_address = "\n".join(p for p in name_addr_parts if p) or "----"

    customer_sample_id = (
        opts.customer_sample_id
        or (sample.parameters or "").strip()
        or (sample.sample_name or "").strip()
        or BLANK_FIELD
    )
    appearance = opts.sample_appearance or (header.appearance_text or "").strip()
    perf_date = opts.test_performance_date
    if not perf_date:
        recv = _fmt_date(header.sample_received_on)
        analysis = _fmt_date(header.date_of_analysis)
        if recv and analysis and recv != analysis:
            perf_date = f"{recv} – {analysis}"
        else:
            perf_date = analysis or recv

    rows_data = [
        ("Customer Name & Address", name_address, None, None),
        ("Customer Sample ID", customer_sample_id, None, None),
        (
            "Lab Code",
            sample.lab_code or sample.sample_code or "",
            "Date of Sample Receipt",
            _fmt_date(header.sample_received_on),
        ),
        (
            "Sample Name",
            sample.sample_name or "",
            "Sample Drawn By",
            _sample_drawn_by(sample),
        ),
        (
            "Condition of Sample",
            opts.condition_of_sample or "",
            "Test Performance Date",
            perf_date,
        ),
        (
            "Appearance",
            appearance,
            "Sample Quantity",
            sample.quantity or "",
        ),
        (
            "Date of Sampling",
            opts.date_of_sampling or BLANK_FIELD,
            "Sampling Done by Laboratory",
            _sampling_done_by_lab(sample),
        ),
        (
            "Location of Sampling",
            opts.location_of_sampling or BLANK_FIELD,
            "Sampling Method",
            opts.sampling_method or BLANK_FIELD,
        ),
    ]

    for i, (l1, v1, l2, v2) in enumerate(rows_data):
        row = table.rows[i]
        if l2 is None:
            # Merge-style: label | value spanning
            _set_cell_text(row.cells[0], l1, bold=True)
            _set_cell_text(row.cells[1], v1)
            if len(row.cells) > 2:
                _set_cell_text(row.cells[2], "")
            if len(row.cells) > 3:
                _set_cell_text(row.cells[3], "")
        else:
            _set_cell_text(row.cells[0], l1, bold=True)
            _set_cell_text(row.cells[1], v1)
            _set_cell_text(row.cells[2], l2, bold=True)
            _set_cell_text(row.cells[3], v2)


def fill_micro_test_report_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    opts: Optional[MicroReportFillOptions] = None,
) -> bytes:
    """Produce a filled micro test report .docx matching the HTML reference."""
    fill_opts = opts or MicroReportFillOptions()
    by_key = {r.test_key: r for r in results}

    if not fill_opts.report_no:
        fill_opts.report_no = _default_report_no(sample)
    if not fill_opts.report_date:
        fill_opts.report_date = header.date_of_analysis or date.today()
    if not fill_opts.sample_appearance:
        fill_opts.sample_appearance = (header.appearance_text or "").strip()

    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.5)

    _add_right(doc, MICRO_REPORT_QSF, size_pt=10)
    _add_centered(doc, "TEST REPORT", size_pt=14, bold=True)

    report_date = _fmt_date(fill_opts.report_date)
    date_report = doc.add_paragraph()
    run = date_report.add_run(
        f"Date: {report_date}"
        f"\t\t\t\t"
        f"Report No: {fill_opts.report_no or ''}"
    )
    _set_run_font(run, size_pt=10)

    meta = doc.add_table(rows=8, cols=4)
    meta.style = "Table Grid"
    _fill_metadata_table(meta, sample, header, fill_opts)

    doc.add_paragraph("")

    selected = set(sample.selected_test_keys()) if sample.tests_json else set(by_key)
    if not selected:
        selected = set(by_key.keys())
    keys = micro_report_keys_ordered(selected)
    if not keys:
        keys = micro_report_keys_ordered(None)

    # Header + section title + one row per test
    results_table = doc.add_table(rows=2 + len(keys), cols=5)
    results_table.style = "Table Grid"

    headers = [
        "Sr. No.",
        "Name of Test",
        "Result",
        "Limits",
        "Method of Analysis",
    ]
    for i, h in enumerate(headers):
        _set_cell_text(results_table.rows[0].cells[i], h, bold=True, size_pt=9)

    # Section row
    section_row = results_table.rows[1]
    _set_cell_text(section_row.cells[0], MICRO_REPORT_SECTION_TITLE, bold=True)
    for i in range(1, 5):
        _set_cell_text(section_row.cells[i], "")

    for idx, key in enumerate(keys):
        spec = spec_for_key(key)
        row = results_table.rows[idx + 2]
        _set_cell_text(row.cells[0], spec.sr_no or str(idx + 1))
        _set_cell_text(row.cells[1], spec.name)
        _set_cell_text(row.cells[2], _result_display(by_key.get(key)))
        _set_cell_text(row.cells[3], spec.limits)
        _set_cell_text(row.cells[4], spec.method, size_pt=8.5)

    doc.add_paragraph("")

    disc = doc.add_table(rows=1, cols=1)
    disc.style = "Table Grid"
    disc_text = "\n".join(MICRO_DISCLAIMER_LINES)
    _set_cell_text(disc.rows[0].cells[0], disc_text, size_pt=9)

    doc.add_paragraph("")
    _add_centered(doc, MICRO_END_OF_REPORT, size_pt=10, bold=False)

    stamp_at = (fill_opts.generated_at or "").strip() or format_stamp_datetime()
    doc.add_paragraph("")
    for line in generator_stamp_lines(fill_opts.generated_by, stamp_at):
        p = doc.add_paragraph()
        run = p.add_run(line)
        _set_run_font(run, size_pt=8)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def suggest_micro_test_report_filename(
    sample: SampleRecord,
    *,
    extension: str = "docx",
) -> str:
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (sample.sample_name or sample.sample_code or "sample")
    )
    ext = extension.lstrip(".")
    return f"MicroTestReport_{safe}_{sample.sample_code}.{ext}"


def generate_micro_test_report_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    opts: Optional[MicroReportFillOptions] = None,
) -> tuple[bytes, bytes | None]:
    """Returns (docx_bytes, pdf_bytes_or_none)."""
    docx_bytes = fill_micro_test_report_docx_bytes(
        sample, header, results, opts=opts
    )
    pdf_bytes = try_convert_docx_to_pdf(docx_bytes)
    return docx_bytes, pdf_bytes
