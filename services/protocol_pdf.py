"""
services/protocol_pdf.py
------------------------
Convert filled protocol .docx to PDF (docx2pdf / Word), with simple fallback note.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from services.protocol_docx import fill_protocol_docx_bytes, suggest_protocol_filename
from services.protocol_store import ProtocolHeader, TestResultRow
from services.samples import SampleRecord

logger = logging.getLogger(__name__)


def generate_protocol_pdf_bytes(
    sample: SampleRecord,
    header: ProtocolHeader,
    results: list[TestResultRow],
    generated_by: str = "",
    generated_at: str = "",
) -> tuple[bytes, str]:
    """
    Returns (pdf_bytes_or_docx_bytes, filename).

    Prefers PDF via Word; if conversion fails, returns the filled DOCX bytes
    with a .docx filename so the analyst can still download.
    """
    docx_bytes = fill_protocol_docx_bytes(
        sample,
        header,
        results,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    docx_name = suggest_protocol_filename(sample)
    pdf_name = docx_name.replace(".docx", ".pdf")

    tmp = tempfile.mkdtemp(prefix="sls_proto_")
    docx_path = Path(tmp) / "protocol.docx"
    pdf_path = Path(tmp) / "protocol.pdf"
    try:
        docx_path.write_bytes(docx_bytes)
        try:
            from docx2pdf import convert

            convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                return pdf_path.read_bytes(), pdf_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("Protocol PDF conversion failed: %s", exc)
        return docx_bytes, docx_name
    finally:
        for p in (docx_path, pdf_path):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass