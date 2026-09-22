"""Unit tests for shared DOCX→PDF conversion and protocol PDF wiring."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from services import ctr_pdf
from services import docx_to_pdf
from services import protocol_pdf
from services.protocol_store import ProtocolHeader, TestResultRow
from services.requests import SampleRow, TestRequestData
from services.samples import SampleRecord
from services.customers import Customer
from tests.conftest import sample_verification_kwargs


def _sample() -> SampleRecord:
    return SampleRecord(
        id=1,
        request_id=1,
        sample_code="SLS-260804-0001",
        sr_no=1,
        sample_name="Test Sauce",
        batch_code="",
        quantity="",
        parameters="",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json='["sulphur_dioxide"]',
        lab_code="LAB/CTR/26/001",
        package_type="",
    )


def _header() -> ProtocolHeader:
    return ProtocolHeader(
        sample_id=1,
        protocol_no="GLG/26/555/01",
        issued_to="Analyst",
        issued_by="Reception",
        sample_received_on=date(2026, 8, 4),
        date_of_analysis=date(2026, 8, 4),
        appearance_text="Normal",
    )


def test_convert_docx_bytes_to_pdf_success(monkeypatch):
    def _fake_word(docx_path, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        return None

    monkeypatch.setattr(docx_to_pdf, "_convert_with_word_subprocess", _fake_word)
    monkeypatch.setattr(docx_to_pdf.sys, "platform", "win32")

    pdf, err = docx_to_pdf.convert_docx_bytes_to_pdf(b"docx")
    assert pdf == b"%PDF-1.4 fake"
    assert err is None


def test_convert_docx_bytes_to_pdf_failure(monkeypatch):
    monkeypatch.setattr(
        docx_to_pdf,
        "_convert_with_word_subprocess",
        lambda _d, _p: "Word busy",
    )
    monkeypatch.setattr(
        docx_to_pdf,
        "_convert_with_libreoffice",
        lambda _d, _p: "LibreOffice not installed",
    )
    monkeypatch.setattr(docx_to_pdf.sys, "platform", "win32")

    pdf, err = docx_to_pdf.convert_docx_bytes_to_pdf(b"docx")
    assert pdf is None
    assert "Word busy" in (err or "")
    assert "LibreOffice" in (err or "")


def test_format_word_conversion_error_call_rejected():
    detail = (
        "Traceback (most recent call last):\n"
        "pywintypes.com_error: (-2147418111, 'Call was rejected by callee.', None, None)"
    )
    msg = docx_to_pdf.format_word_conversion_error(detail)
    assert msg == docx_to_pdf._WORD_BUSY_MESSAGE
    assert "Traceback" not in msg


def test_format_word_conversion_error_other():
    msg = docx_to_pdf.format_word_conversion_error("Word did not create the PDF file")
    assert msg == "Microsoft Word conversion failed: Word did not create the PDF file"


def test_convert_with_word_subprocess_maps_call_rejected(monkeypatch, tmp_path):
    docx_path = tmp_path / "in.docx"
    pdf_path = tmp_path / "out.pdf"
    docx_path.write_bytes(b"docx")

    proc = MagicMock(
        returncode=1,
        stdout="",
        stderr=(
            "pywintypes.com_error: (-2147418111, 'Call was rejected by callee.', None, None)"
        ),
    )
    monkeypatch.setattr(docx_to_pdf.subprocess, "run", lambda *a, **k: proc)

    err = docx_to_pdf._convert_with_word_subprocess(docx_path, pdf_path)
    assert err == docx_to_pdf._WORD_BUSY_MESSAGE


def test_try_convert_docx_to_pdf_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(
        docx_to_pdf,
        "convert_docx_bytes_to_pdf",
        lambda _b: (None, "conversion failed"),
    )
    assert docx_to_pdf.try_convert_docx_to_pdf(b"x") is None


def test_generate_protocol_documents_returns_pdf_and_error(monkeypatch):
    fake_docx = b"PK fake docx"
    fake_pdf = b"%PDF fake"

    monkeypatch.setattr(
        protocol_pdf,
        "generate_protocol_docx_bytes",
        lambda *a, **k: fake_docx,
    )
    monkeypatch.setattr(
        protocol_pdf,
        "convert_docx_bytes_to_pdf",
        lambda _b: (fake_pdf, None),
    )
    monkeypatch.setattr(
        protocol_pdf,
        "suggest_protocol_filename",
        lambda _s: "Protocol_Test.docx",
    )

    docx, pdf, docx_name, pdf_name, pdf_err = protocol_pdf.generate_protocol_documents(
        _sample(), _header(), []
    )
    assert docx == fake_docx
    assert pdf == fake_pdf
    assert docx_name == "Protocol_Test.docx"
    assert pdf_name == "Protocol_Test.pdf"
    assert pdf_err is None


def test_generate_protocol_documents_propagates_pdf_error(monkeypatch):
    monkeypatch.setattr(
        protocol_pdf,
        "generate_protocol_docx_bytes",
        lambda *a, **k: b"docx",
    )
    monkeypatch.setattr(
        protocol_pdf,
        "convert_docx_bytes_to_pdf",
        lambda _b: (None, "Microsoft Word conversion failed: busy"),
    )
    monkeypatch.setattr(
        protocol_pdf,
        "suggest_protocol_filename",
        lambda _s: "Protocol_Test.docx",
    )

    _docx, pdf, _docx_name, _pdf_name, pdf_err = protocol_pdf.generate_protocol_documents(
        _sample(), _header(), []
    )
    assert pdf is None
    assert pdf_err == "Microsoft Word conversion failed: busy"


def _ctr_request() -> TestRequestData:
    return TestRequestData(
        customer=Customer(
            customer_name="ABC Foods",
            address="1 Lab Road",
            contact_person="Ravi",
            contact_number="9876543210",
            email="ravi@example.com",
            gst_number="27AAAAA0000A1Z5",
        ),
        request_date=date(2026, 7, 30),
        lab_code="LAB/CTR/26/001",
        samples=[
            SampleRow(
                sr_no=1,
                sample_name="sauce",
                batch_code="01",
                quantity="100gm",
                test_keys=["moisture"],
                **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
            ),
        ],
    )


def test_generate_ctr_documents_returns_pdf_and_error(monkeypatch):
    fake_docx = b"PK fake ctr docx"
    fake_pdf = b"%PDF fake ctr"

    monkeypatch.setattr(
        ctr_pdf,
        "fill_docx_bytes",
        lambda *a, **k: fake_docx,
    )
    monkeypatch.setattr(
        ctr_pdf,
        "convert_docx_bytes_to_pdf",
        lambda b: (fake_pdf, None),
    )
    monkeypatch.setattr(
        ctr_pdf,
        "generate_pdf_bytes",
        lambda *a, **k: fake_pdf,
    )
    monkeypatch.setattr(
        ctr_pdf,
        "suggest_docx_filename",
        lambda _d: "CTR_ABC.docx",
    )
    monkeypatch.setattr(
        ctr_pdf,
        "suggest_pdf_filename",
        lambda _d: "CTR_ABC.pdf",
    )

    docx, pdf, docx_name, pdf_name, pdf_err = ctr_pdf.generate_ctr_documents(
        _ctr_request(), generated_by="Reception User"
    )
    assert docx == fake_docx
    assert pdf == fake_pdf
    assert docx_name == "CTR_ABC.docx"
    assert pdf_name == "CTR_ABC.pdf"
    assert pdf_err is None


def test_generate_ctr_documents_propagates_pdf_error(monkeypatch):
    monkeypatch.setattr(ctr_pdf, "fill_docx_bytes", lambda *a, **k: b"docx")
    monkeypatch.setattr(
        ctr_pdf,
        "convert_docx_bytes_to_pdf",
        lambda b: (None, "Word not available"),
    )

    def _boom(*a, **k):
        raise RuntimeError("ReportLab failed")

    monkeypatch.setattr(ctr_pdf, "generate_pdf_bytes", _boom)
    monkeypatch.setattr(ctr_pdf, "suggest_docx_filename", lambda _d: "CTR.docx")
    monkeypatch.setattr(ctr_pdf, "suggest_pdf_filename", lambda _d: "CTR.pdf")

    _docx, pdf, _dn, _pn, pdf_err = ctr_pdf.generate_ctr_documents(_ctr_request())
    assert pdf is None
    assert "Word not available" in (pdf_err or "")
    assert "ReportLab failed" in (pdf_err or "")


def test_word_child_script_uses_subprocess(monkeypatch, tmp_path):
    docx_path = tmp_path / "in.docx"
    pdf_path = tmp_path / "out.pdf"
    docx_path.write_bytes(b"docx")
    pdf_path.write_bytes(b"%PDF")

    proc = MagicMock(returncode=0)
    monkeypatch.setattr(docx_to_pdf.subprocess, "run", lambda *a, **k: proc)

    err = docx_to_pdf._convert_with_word_subprocess(docx_path, pdf_path)
    assert err is None
