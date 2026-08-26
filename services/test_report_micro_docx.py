"""
services/test_report_micro_docx.py
----------------------------------
Fill reference/Micro Test Report.docx for Micro final test reports.

Layout (margins, row heights, fonts) is taken from the reference template.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Optional

from services.docx_layout import (
    clear_header_images,
    combine_docx_bytes,
    delete_table_rows_range,
    finalize_docx_document,
    load_template,
    set_cell_text,
    set_report_footer,
)
from services.docx_to_pdf import try_convert_docx_to_pdf
from services.micro_report_catalog import (
    MICRO_DISCLAIMER_LINES,
    micro_report_keys_ordered,
    spec_for_key,
)
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import (
    REPORT_FORMAT_BOTH,
    SampleRecord,
    default_report_with_logo,
    default_test_report_no,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MICRO_REPORT_TEMPLATE_PATH = PROJECT_ROOT / "reference" / "Micro Test Report.docx"

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


def _default_report_no(sample: SampleRecord, *, with_logo: bool | None = None) -> str:
    logo_flag = default_report_with_logo(sample) if with_logo is None else with_logo
    return default_test_report_no(sample, with_logo=logo_flag)


def _result_display(res: Optional[TestResultRow]) -> str:
    from services.number_format import format_report_number

    if res is None:
        return ""
    val = (res.result_value or "").strip()
    if not val:
        return ""
    formatted = format_report_number(val)
    unit = (res.unit or "").strip()
    if unit and unit.lower() not in formatted.lower():
        return f"{formatted} {unit}".strip()
    return formatted


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
        ("Customer Name & Address", name_address),
        ("Customer Sample ID", customer_sample_id),
        ("Lab Code", sample.lab_code or sample.sample_code or "", "Date of Sample Receipt", _fmt_date(header.sample_received_on)),
        ("Sample Name", sample.sample_name or "", "Sample Drawn By", _sample_drawn_by(sample)),
        ("Condition of Sample", opts.condition_of_sample or "", "Test Performance Date", perf_date),
        ("Appearance", appearance, "Sample Quantity", sample.quantity or ""),
        ("Date of Sampling", opts.date_of_sampling or BLANK_FIELD, "Sampling Done by Laboratory", _sampling_done_by_lab(sample)),
        ("Location of Sampling", opts.location_of_sampling or BLANK_FIELD, "Sampling Method", opts.sampling_method or BLANK_FIELD),
    ]

    for i, row_data in enumerate(rows_data):
        row = table.rows[i]
        if len(row_data) == 2:
            set_cell_text(row.cells[0], row_data[0])
            set_cell_text(row.cells[1], row_data[1])
            set_cell_text(row.cells[2], "")
            set_cell_text(row.cells[3], "")
        else:
            set_cell_text(row.cells[0], row_data[0])
            set_cell_text(row.cells[1], row_data[1])
            set_cell_text(row.cells[2], row_data[2])
            set_cell_text(row.cells[3], row_data[3])


def fill_micro_test_report_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    opts: Optional[MicroReportFillOptions] = None,
    *,
    test_key_filter: Optional[set[str]] = None,
    with_logo: bool | None = None,
) -> bytes:
    """Produce a filled micro test report .docx from the reference template."""
    if not MICRO_REPORT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Micro test report template missing: {MICRO_REPORT_TEMPLATE_PATH}"
        )

    fill_opts = opts or MicroReportFillOptions()
    by_key = {r.test_key: r for r in results}
    logo_flag = default_report_with_logo(sample) if with_logo is None else with_logo

    if not fill_opts.report_no:
        fill_opts.report_no = _default_report_no(sample, with_logo=logo_flag)
    if not fill_opts.report_date:
        fill_opts.report_date = header.date_of_analysis or date.today()
    if not fill_opts.sample_appearance:
        fill_opts.sample_appearance = (header.appearance_text or "").strip()

    doc = load_template(MICRO_REPORT_TEMPLATE_PATH)
    if not logo_flag:
        clear_header_images(doc)
    tables = doc.tables
    if len(tables) < 4:
        raise ValueError("Micro Test Report.docx must have 4 tables.")

    # Table 0 — Date / Report No
    set_cell_text(tables[0].rows[0].cells[0], f"Date: {_fmt_date(fill_opts.report_date)}")
    set_cell_text(
        tables[0].rows[0].cells[1],
        f"Report No: {fill_opts.report_no or ''}",
    )

    _fill_metadata_table(tables[1], sample, header, fill_opts)

    selected = set(sample.selected_test_keys()) if sample.tests_json else set(by_key)
    if not selected:
        selected = set(by_key.keys())
    if test_key_filter is not None:
        selected &= test_key_filter
    keys = micro_report_keys_ordered(selected)
    if not keys:
        keys = micro_report_keys_ordered(test_key_filter)

    results_table = tables[2]
    n_keys = len(keys)
    for idx, key in enumerate(keys):
        row_idx = idx + 2
        if row_idx >= len(results_table.rows):
            break
        spec = spec_for_key(key)
        row = results_table.rows[row_idx]
        set_cell_text(row.cells[0], spec.sr_no or str(idx + 1))
        set_cell_text(row.cells[1], spec.name)
        set_cell_text(row.cells[2], _result_display(by_key.get(key)))
        set_cell_text(row.cells[3], spec.limits)
        set_cell_text(row.cells[4], spec.method)

    delete_table_rows_range(results_table, 2 + n_keys, len(results_table.rows))

    disc_text = "Disclaimer:\n" + "\n".join(
        f"{i + 1}.{line}" for i, line in enumerate(MICRO_DISCLAIMER_LINES)
    )
    set_cell_text(tables[3].rows[0].cells[0], disc_text)

    set_report_footer(doc, with_logo=logo_flag)

    finalize_docx_document(doc, set_qsf=True)

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
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_BOTH:
        parts: list[bytes] = []
        logo_flags: list[bool] = []
        base_opts = opts or MicroReportFillOptions()
        if logo_test_keys(sample):
            logo_opts = replace(
                base_opts,
                report_no=base_opts.report_no
                or _default_report_no(sample, with_logo=True),
            )
            parts.append(
                fill_micro_test_report_docx_bytes(
                    sample,
                    header,
                    results,
                    opts=logo_opts,
                    test_key_filter=logo_test_keys(sample),
                    with_logo=True,
                )
            )
            logo_flags.append(True)
        if no_logo_test_keys(sample):
            nologo_opts = replace(
                base_opts,
                report_no=_default_report_no(sample, with_logo=False),
            )
            parts.append(
                fill_micro_test_report_docx_bytes(
                    sample,
                    header,
                    results,
                    opts=nologo_opts,
                    test_key_filter=no_logo_test_keys(sample),
                    with_logo=False,
                )
            )
            logo_flags.append(False)
        docx_bytes = (
            combine_docx_bytes(parts, with_logo_per_section=logo_flags)
            if parts
            else fill_micro_test_report_docx_bytes(sample, header, results, opts=opts)
        )
    else:
        docx_bytes = fill_micro_test_report_docx_bytes(
            sample, header, results, opts=opts
        )
    pdf_bytes = try_convert_docx_to_pdf(docx_bytes)
    return docx_bytes, pdf_bytes
