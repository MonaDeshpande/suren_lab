"""
services/ctr_pdf.py
-------------------
Generate filled Customer Test Request Word + PDF.

PDF: prefer Word→PDF from filled DOCX (CTR_template header on every page).
Fallback: ReportLab layout when conversion fails (no Word letterhead).
DOCX: Word LLP template + cloned header only from reference/CTR_template.docx.
"""

from __future__ import annotations

import logging

from services.docx_filler import fill_docx_bytes, suggest_docx_filename
from services.docx_to_pdf import convert_docx_bytes_to_pdf
from services.pdf_generator import generate_pdf_bytes, suggest_pdf_filename
from services.requests import TestRequestData

logger = logging.getLogger(__name__)


def generate_ctr_documents(
    data: TestRequestData,
    generated_by: str = "",
    generated_at: str = "",
) -> tuple[bytes, bytes | None, str, str, str | None]:
    """
    Returns (docx_bytes, pdf_bytes_or_none, docx_filename, pdf_filename, pdf_error).

    PDF is exported from the filled DOCX when Word/LibreOffice conversion succeeds
    (same CTR_template.docx header as the Word download). Otherwise ReportLab fallback.
    """
    docx_bytes = fill_docx_bytes(
        data, generated_by=generated_by, generated_at=generated_at
    )
    docx_name = suggest_docx_filename(data)
    pdf_name = suggest_pdf_filename(data)
    pdf_bytes, convert_err = convert_docx_bytes_to_pdf(docx_bytes)
    if pdf_bytes:
        return docx_bytes, pdf_bytes, docx_name, pdf_name, None
    if convert_err:
        logger.warning("CTR DOCX→PDF failed, using ReportLab fallback: %s", convert_err)
    try:
        pdf_bytes = generate_pdf_bytes(
            data, generated_by=generated_by, generated_at=generated_at
        )
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        if convert_err:
            err = f"{convert_err} ReportLab fallback also failed: {err}"
        return docx_bytes, None, docx_name, pdf_name, err
    return docx_bytes, pdf_bytes, docx_name, pdf_name, None
