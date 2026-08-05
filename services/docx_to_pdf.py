"""
services/docx_to_pdf.py
-----------------------
Convert filled .docx bytes to PDF via Microsoft Word (Windows subprocess) or
LibreOffice headless fallback.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Isolated child process — avoids Streamlit/COM threading issues on Windows.
_WORD_CHILD_SCRIPT = r"""
import sys
import time
from pathlib import Path

docx_path = str(Path(sys.argv[1]).resolve())
pdf_path = str(Path(sys.argv[2]).resolve())

import pythoncom

pythoncom.CoInitialize()
word = None
doc = None
try:
    import win32com.client

    word = win32com.client.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    time.sleep(0.5)

    last_open_err = None
    for attempt in range(3):
        try:
            doc = word.Documents.Open(docx_path)
            if doc is None:
                raise RuntimeError("Word did not open the document")
            last_open_err = None
            break
        except Exception as exc:
            last_open_err = exc
            time.sleep(1.5 * (attempt + 1))
    if last_open_err is not None:
        raise SystemExit(f"Word Open failed: {last_open_err}")

    try:
        try:
            doc.SaveAs(pdf_path, FileFormat=17)
        except Exception:
            doc.ExportAsFixedFormat(pdf_path, 17)
    finally:
        doc.Close(0)
finally:
    if word is not None:
        try:
            word.Quit()
        except Exception:
            pass
    pythoncom.CoUninitialize()

if not Path(pdf_path).is_file():
    raise SystemExit("Word did not create the PDF file")
"""


def word_pdf_available() -> bool:
    """True when Word (Windows) or LibreOffice conversion is likely available."""
    if sys.platform == "win32":
        return True
    return shutil.which("soffice") is not None


def _convert_with_word_subprocess(docx_path: Path, pdf_path: Path) -> str | None:
    """Run Word COM in a fresh Python process. Returns error text or None."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _WORD_CHILD_SCRIPT, str(docx_path), str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Word PDF conversion timed out after 120 seconds"
    except OSError as exc:
        return f"Could not start Word conversion process: {exc}"

    if proc.returncode == 0 and pdf_path.is_file():
        return None

    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = f"exit code {proc.returncode}"
    return f"Microsoft Word conversion failed: {detail}"


def _convert_with_libreoffice(docx_path: Path, pdf_path: Path) -> str | None:
    """LibreOffice headless fallback. Returns error text or None."""
    soffice = shutil.which("soffice")
    if not soffice:
        return "LibreOffice (soffice) is not installed"

    out_dir = pdf_path.parent
    try:
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(docx_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "LibreOffice PDF conversion timed out after 120 seconds"
    except OSError as exc:
        return f"Could not start LibreOffice: {exc}"

    produced = out_dir / f"{docx_path.stem}.pdf"
    if proc.returncode == 0 and produced.is_file():
        if produced != pdf_path:
            produced.replace(pdf_path)
        return None

    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = f"exit code {proc.returncode}"
    return f"LibreOffice conversion failed: {detail}"


def convert_docx_bytes_to_pdf(docx_bytes: bytes) -> tuple[bytes | None, str | None]:
    """
    Convert .docx bytes to PDF.

    Returns (pdf_bytes, error_message). error_message is None on success.
    """
    tmp = tempfile.mkdtemp(prefix="sls_docx_pdf_")
    docx_path = Path(tmp) / "document.docx"
    pdf_path = Path(tmp) / "document.pdf"
    errors: list[str] = []

    try:
        docx_path.write_bytes(docx_bytes)

        if sys.platform == "win32":
            word_err = _convert_with_word_subprocess(docx_path, pdf_path)
            if word_err is None and pdf_path.is_file():
                return pdf_path.read_bytes(), None
            if word_err:
                errors.append(word_err)
                logger.warning("Word PDF conversion failed (attempt 1): %s", word_err)
                time.sleep(1.0)
                pdf_path.unlink(missing_ok=True)
                word_err = _convert_with_word_subprocess(docx_path, pdf_path)
                if word_err is None and pdf_path.is_file():
                    return pdf_path.read_bytes(), None
                if word_err:
                    errors.append(f"retry: {word_err}")
                    logger.warning("Word PDF conversion failed (attempt 2): %s", word_err)

        lo_err = _convert_with_libreoffice(docx_path, pdf_path)
        if lo_err is None and pdf_path.is_file():
            return pdf_path.read_bytes(), None
        if lo_err:
            errors.append(lo_err)

        if sys.platform != "win32" and not errors:
            errors.append("PDF conversion is only supported on Windows (Word) or with LibreOffice")

        return None, "; ".join(errors) if errors else "PDF conversion failed"
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


def try_convert_docx_to_pdf(docx_bytes: bytes) -> bytes | None:
    """Legacy helper — returns PDF bytes or None (errors logged only)."""
    pdf_bytes, err = convert_docx_bytes_to_pdf(docx_bytes)
    if err:
        logger.warning("DOCX to PDF conversion failed: %s", err)
    return pdf_bytes
