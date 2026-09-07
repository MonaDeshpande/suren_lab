"""
services/docx_to_pdf.py
-----------------------
Convert filled .docx bytes to PDF via Microsoft Word (Windows subprocess) or
LibreOffice headless fallback.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from services.docx_layout import rewrite_unicode_scripts_in_docx_bytes

logger = logging.getLogger(__name__)
_DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "debug-3467ee.log"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "3467ee",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except OSError:
        pass
    # endregion

# RPC_E_CALL_REJECTED — Word busy / dialog open / reused instance not responding.
_WORD_CALL_REJECTED_MARKERS = (
    "Call was rejected by callee",
    "-2147418111",
    "RPC_E_CALL_REJECTED",
)

_WORD_BUSY_MESSAGE = (
    "Microsoft Word was busy and rejected PDF export. "
    "Close any Word dialogs/windows and try again."
)

# Isolated child process — avoids Streamlit/COM threading issues on Windows.
_WORD_CHILD_SCRIPT = r"""
import sys
import time
from pathlib import Path

docx_path = str(Path(sys.argv[1]).resolve())
pdf_path = str(Path(sys.argv[2]).resolve())

import pythoncom

CALL_REJECTED = -2147418111


def _is_call_rejected(exc):
    if getattr(exc, "hresult", None) == CALL_REJECTED:
        return True
    text = str(exc)
    return "Call was rejected by callee" in text or str(CALL_REJECTED) in text


def _retry_com(action, attempts=3, base_delay=1.0):
    last_exc = None
    for attempt in range(attempts):
        try:
            return action()
        except Exception as exc:
            last_exc = exc
            if not _is_call_rejected(exc) or attempt >= attempts - 1:
                raise
            time.sleep(base_delay * (attempt + 1))
    raise last_exc


pythoncom.CoInitialize()
word = None
doc = None
try:
    import win32com.client

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    time.sleep(0.5)

    def _open_doc():
        opened = word.Documents.Open(
            docx_path,
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
        )
        if opened is None:
            raise RuntimeError("Word did not open the document")
        return opened

    doc = _retry_com(_open_doc)

    def _export_pdf():
        try:
            doc.ExportAsFixedFormat(
                OutputFileName=pdf_path,
                ExportFormat=17,
                OpenAfterExport=False,
                OptimizeFor=0,
            )
        except Exception:
            doc.SaveAs(pdf_path, FileFormat=17)

    _retry_com(_export_pdf)
finally:
    if doc is not None:
        try:
            _retry_com(lambda: doc.Close(False), attempts=2, base_delay=0.5)
        except Exception:
            pass
    if word is not None:
        try:
            _retry_com(lambda: word.Quit(), attempts=2, base_delay=0.5)
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


def _is_word_call_rejected(detail: str) -> bool:
    lower = (detail or "").lower()
    return any(marker.lower() in lower for marker in _WORD_CALL_REJECTED_MARKERS)


def format_word_conversion_error(detail: str) -> str:
    """
    Collapse noisy Word COM tracebacks into a short UI-friendly message.

    Full detail should still be logged by the caller.
    """
    if _is_word_call_rejected(detail):
        return _WORD_BUSY_MESSAGE
    stripped = (detail or "").strip()
    if not stripped:
        return "Microsoft Word conversion failed"
    return f"Microsoft Word conversion failed: {stripped}"


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
    friendly = format_word_conversion_error(detail)
    if friendly != detail and not friendly.startswith("Microsoft Word conversion failed:"):
        logger.warning("Word PDF conversion failed (full detail): %s", detail)
    return friendly


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
        docx_bytes = rewrite_unicode_scripts_in_docx_bytes(docx_bytes)
        docx_path.write_bytes(docx_bytes)

        if sys.platform == "win32":
            word_err = _convert_with_word_subprocess(docx_path, pdf_path)
            _debug_log(
                hypothesis_id="B",
                location="docx_to_pdf.py:convert_docx_bytes_to_pdf",
                message="word conversion attempt 1",
                data={
                    "docx_bytes": len(docx_bytes),
                    "word_err": word_err,
                    "pdf_created": pdf_path.is_file(),
                },
            )
            if word_err is None and pdf_path.is_file():
                return pdf_path.read_bytes(), None
            if word_err:
                errors.append(word_err)
                logger.warning("Word PDF conversion failed (attempt 1): %s", word_err)
                time.sleep(2.0)
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
