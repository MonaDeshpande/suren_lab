"""
services/protocol_pdf.py
------------------------
Convert filled protocol .docx to PDF (Word / LibreOffice via services/docx_to_pdf).
"""

from __future__ import annotations

from services.docx_to_pdf import convert_docx_bytes_to_pdf
from services.protocol_docx import fill_protocol_docx_bytes, suggest_protocol_filename
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord


def generate_protocol_docx_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    generated_by: str = "",
    generated_at: str = "",
) -> bytes:
    """Filled protocol Word document."""
    return fill_protocol_docx_bytes(
        sample,
        header,
        results,
        generated_by=generated_by,
        generated_at=generated_at,
    )


def generate_protocol_documents(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    generated_by: str = "",
    generated_at: str = "",
) -> tuple[bytes, bytes | None, str, str, str | None]:
    """
    Returns (docx_bytes, pdf_bytes_or_none, docx_filename, pdf_filename, pdf_error).
    pdf_error is None when PDF conversion succeeded.
    """
    docx_bytes = generate_protocol_docx_bytes(
        sample,
        header,
        results,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    docx_name = suggest_protocol_filename(sample)
    pdf_name = docx_name.replace(".docx", ".pdf")
    pdf_bytes, pdf_error = convert_docx_bytes_to_pdf(docx_bytes)
    return docx_bytes, pdf_bytes, docx_name, pdf_name, pdf_error


def generate_protocol_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    generated_by: str = "",
    generated_at: str = "",
) -> tuple[bytes, str]:
    """
    Legacy helper — returns PDF bytes when possible, else DOCX bytes.

    Prefer generate_protocol_documents() for explicit Word + PDF downloads.
    """
    docx_bytes, pdf_bytes, docx_name, pdf_name, _pdf_error = generate_protocol_documents(
        sample,
        header,
        results,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    if pdf_bytes is not None:
        return pdf_bytes, pdf_name
    return docx_bytes, docx_name
