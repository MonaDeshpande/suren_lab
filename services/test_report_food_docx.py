"""
services/test_report_food_docx.py
---------------------------------
Fill reference/Test Report Format.docx for food final reports.

Page layout (margins, fonts, table geometry) comes from the DK Brothers reference;
only data cells are replaced at generation time.
"""

from __future__ import annotations

import io
import logging
from datetime import date
from typing import Optional

from services.document_templates import (
    FOOD_REPORT_TEMPLATE_PATH,
    final_report_template_path,
)
from services.docx_layout import (
    combine_docx_bytes,
    compact_single_page_document,
    delete_table_rows_range,
    fill_report_signature_block,
    finalize_docx_document,
    insert_table_row_before,
    load_template,
    set_cell_text,
    set_paragraph_by_marker,
    set_paragraph_text,
    set_report_footer,
)
from services.samples import (
    REPORT_FORMAT_BOTH,
    SampleRecord,
    default_report_with_logo,
    logo_test_keys,
    no_logo_test_keys,
    normalize_report_format,
)
from services.docx_to_pdf import try_convert_docx_to_pdf
from services.protocol_store import ProtocolHeader, TestResultRow
from services.test_report_pdf import (
    TestReportData,
    build_test_report_data,
    suggest_test_report_filename,
)

logger = logging.getLogger(__name__)

HEADER_ROW_COUNT = 2
FIRST_DATA_ROW = 2


def _metadata_table(doc) -> object | None:
    return doc.tables[0] if doc.tables else None


def _results_table(doc) -> object | None:
    return doc.tables[1] if len(doc.tables) > 1 else None


def _fill_metadata_table(table, data: TestReportData) -> None:
    if len(table.rows) < 9:
        return
    rows = [
        ("Customer Name & Address", data.customer_name_address, "", ""),
        ("Customer Sample ID", data.customer_sample_id, "Batch No.", data.batch_no),
        ("Lab Code ", data.lab_code, "Date of Sample Receipt", data.date_of_sample_receipt),
        ("Sample Name", data.sample_name, "Sample Drawn By", data.sample_drawn_by),
        (
            "Condition Of Sample",
            data.condition_of_sample,
            "Test Performance Date",
            data.test_performance_date,
        ),
        ("Tests processed", data.tests_processed, "Sample quantity", data.sample_quantity),
        ("Appearance", data.appearance, "", ""),
        (
            "Date of Sampling",
            data.date_of_sampling,
            "Sampling Done by",
            data.sampling_done_by,
        ),
        (
            "Location of sampling",
            data.location_of_sampling,
            "Sampling Method",
            data.sampling_method,
        ),
    ]
    for i, (l1, v1, l2, v2) in enumerate(rows):
        row = table.rows[i]
        set_cell_text(row.cells[0], l1)
        set_cell_text(row.cells[1], v1)
        if l2:
            set_cell_text(row.cells[2], l2)
            set_cell_text(row.cells[3], v2)
        else:
            set_cell_text(row.cells[2], "")
            set_cell_text(row.cells[3], "")


def _fill_results_table(table, data: TestReportData) -> None:
    if len(table.rows) < HEADER_ROW_COUNT + 2:
        return
    specs_text = (
        "Specifications\n"
        + (data.specs_header or "").replace("Specifications ", "").replace(
            "Specifications", ""
        ).strip()
    )
    if not specs_text.strip() or specs_text.strip() == "Specifications":
        specs_text = (
            "Specifications\n"
            "FSSAI 2006, Rules & Regulations, Latest Amendments Up to 12/08/2025"
        )
    for hi in range(HEADER_ROW_COUNT):
        if len(table.rows[hi].cells) >= 4:
            set_cell_text(table.rows[hi].cells[3], specs_text)

    remark_row_index = len(table.rows) - 1
    first_data = FIRST_DATA_ROW
    available = remark_row_index - first_data
    n = len(data.rows)
    if n > available:
        for _ in range(n - available):
            insert_table_row_before(table, remark_row_index, first_data)
        remark_row_index = len(table.rows) - 1

    for i, row in enumerate(data.rows):
        tr = table.rows[first_data + i]
        set_cell_text(tr.cells[0], str(row.sr_no))
        set_cell_text(tr.cells[1], row.test_name)
        set_cell_text(tr.cells[2], row.result)
        set_cell_text(tr.cells[3], row.specification)
        set_cell_text(tr.cells[4], row.method)

    delete_table_rows_range(table, first_data + n, len(table.rows) - 1)
    remark_row_index = len(table.rows) - 1

    remark_body = (data.remark_text or "").strip()
    if remark_body.lower().startswith("remark:"):
        remark_body = remark_body[7:].lstrip()
    set_cell_text(table.rows[remark_row_index].cells[1], f"Remark: {remark_body}")


def _fill_identity_paragraphs(
    doc, data: TestReportData, *, with_logo: bool
) -> None:
    if with_logo:
        set_paragraph_by_marker(doc, "ULR No", f"ULR No: {data.ulr_no}")
    else:
        set_paragraph_by_marker(doc, "ULR No", "")
        for para in doc.paragraphs:
            if (para.text or "").strip().startswith("ULR No"):
                set_paragraph_text(para, "")
                break
    for para in doc.paragraphs:
        text = para.text or ""
        if text.startswith("Date:") and "Report No:" in text:
            set_paragraph_text(
                para,
                f"Date: {data.report_date or '--/--/----'}"
                "\t\t\t\t                                  "
                f"Report No: {data.report_no or '---/26/---/--/--'}",
            )
            break


def _fill_signature_block(doc, data: TestReportData) -> None:
    fill_report_signature_block(
        doc,
        authorized_name=data.authorized_signatory,
        authorized_role=data.authorized_signatory_role,
        checked_name=data.checked_by,
        checked_role=data.checked_by_role,
    )


def _fill_disclaimer(doc, data: TestReportData) -> None:
    bullets = data.disclaimer_bullets or []
    if not bullets:
        return
    disc_started = False
    bullet_idx = 0
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text == "Disclaimer" or text.startswith("Disclaimer"):
            disc_started = True
            set_paragraph_text(para, "Disclaimer")
            continue
        if not disc_started:
            continue
        if text == "End of Report":
            break
        if bullet_idx < len(bullets):
            set_paragraph_text(para, bullets[bullet_idx])
            bullet_idx += 1


def fill_food_test_report_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    *,
    report_date: Optional[date] = None,
    generated_by: str = "",
    generated_at: str = "",
    condition_of_sample: str | None = None,
    tests_processed: str | None = None,
    specification_by_test_name: dict[str, str] | None = None,
    row_filter: Optional[set[str]] = None,
    with_logo: bool | None = None,
    ulr_no: str | None = None,
    location_of_sampling: str | None = None,
    sampling_method: str | None = None,
    authorized_signatory: str | None = None,
    checked_by: str | None = None,
    remark_text: str | None = None,
    disclaimer_bullets: list[str] | None = None,
) -> bytes:
    """Produce a filled food test report .docx from the reference template."""
    logo_flag = default_report_with_logo(sample) if with_logo is None else with_logo
    template_path = final_report_template_path(sample.category, with_logo=logo_flag)
    if not template_path.exists():
        raise FileNotFoundError(
            f"Food test report template missing: {template_path}"
        )
    data = build_test_report_data(
        sample,
        header,
        results,
        report_date=report_date,
        generated_by=generated_by,
        generated_at=generated_at,
        condition_of_sample=condition_of_sample,
        tests_processed=tests_processed,
        specification_by_test_name=specification_by_test_name,
        row_filter=row_filter,
        with_logo=logo_flag,
        ulr_no=ulr_no,
        location_of_sampling=location_of_sampling,
        sampling_method=sampling_method,
        authorized_signatory=authorized_signatory,
        checked_by=checked_by,
        remark_text=remark_text,
        disclaimer_bullets=disclaimer_bullets,
    )

    doc = load_template(template_path)

    _fill_identity_paragraphs(doc, data, with_logo=logo_flag)

    meta = _metadata_table(doc)
    if meta is not None:
        _fill_metadata_table(meta, data)

    results_tbl = _results_table(doc)
    if results_tbl is not None:
        _fill_results_table(results_tbl, data)

    _fill_signature_block(doc, data)
    _fill_disclaimer(doc, data)

    compact_single_page_document(doc)
    set_report_footer(doc, with_logo=logo_flag, static_one_of_one=True)

    finalize_docx_document(doc, set_qsf=True)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def generate_food_test_report_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    **kwargs,
) -> tuple[bytes, bytes | None]:
    """Returns (docx_bytes, pdf_bytes_or_none)."""
    fmt = normalize_report_format(sample.report_format)
    if fmt == REPORT_FORMAT_BOTH:
        parts: list[bytes] = []
        logo_flags: list[bool] = []
        if logo_test_keys(sample):
            parts.append(
                fill_food_test_report_docx_bytes(
                    sample,
                    header,
                    results,
                    row_filter=logo_test_keys(sample),
                    with_logo=True,
                    **kwargs,
                )
            )
            logo_flags.append(True)
        if no_logo_test_keys(sample):
            parts.append(
                fill_food_test_report_docx_bytes(
                    sample,
                    header,
                    results,
                    row_filter=no_logo_test_keys(sample),
                    with_logo=False,
                    **kwargs,
                )
            )
            logo_flags.append(False)
        docx_bytes = (
            combine_docx_bytes(
                parts,
                with_logo_per_section=logo_flags,
                static_one_of_one=True,
            )
            if parts
            else fill_food_test_report_docx_bytes(sample, header, results, **kwargs)
        )
    else:
        docx_bytes = fill_food_test_report_docx_bytes(
            sample, header, results, **kwargs
        )
    pdf_bytes = try_convert_docx_to_pdf(docx_bytes)
    return docx_bytes, pdf_bytes


def suggest_food_test_report_docx_filename(sample: SampleRecord) -> str:
    base = suggest_test_report_filename(sample)
    if base.endswith(".pdf"):
        return base[:-4] + ".docx"
    return base + ".docx" if not base.endswith(".docx") else base
