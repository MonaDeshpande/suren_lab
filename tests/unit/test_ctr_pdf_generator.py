"""Unit tests for CTR PDF (ReportLab legacy) and DOCX→PDF document bundle."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from pypdf import PdfReader

from services import ctr_pdf
from services.customers import Customer
from services.protocols.test_catalog import WATER_TEST_KEYS, WATER_MICRO_TEST_KEYS
from services.pdf_generator import (
    _ctr_footer_left,
    _generate_ctr_pdf,
    ctr_total_pages,
    generate_pdf_bytes,
)
from services.requests import SampleRow, TestRequestData
from tests.conftest import sample_verification_kwargs


def _ctr_request(*, samples: list[SampleRow] | None = None) -> TestRequestData:
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
        number_of_samples=1,
        sampling_by_lab=True,
        decision_rule=True,
        service_type="regular",
        delivery_mode="collect",
        samples=samples
        or [
            SampleRow(
                sr_no=1,
                sample_name="sauce",
                batch_code="01",
                quantity="100gm",
                parameters="FSSAI",
                package_type="fssai",
                test_keys=["moisture"],
                **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
            ),
        ],
    )


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestCtrPdfGenerator:
    def test_ctr_pdf_has_no_literal_html_tags(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        text = _pdf_text(pdf)
        assert "<b>" not in text
        assert "</b>" not in text
        assert "<br/>" not in text
        assert "&amp;" not in text

    def test_ctr_pdf_renders_signature_block(self):
        pdf = _generate_ctr_pdf(
            _ctr_request(),
            generated_by="Priya Reception",
            generated_at="2026-09-22 12:00",
        )
        text = _pdf_text(pdf)
        assert "Receiver's Sign" not in text
        assert "Receiver" in text
        assert "Priya Reception" in text
        assert "Customer Signature" in text

    def test_ctr_yes_no_single_brackets_only(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        text = _pdf_text(pdf)
        assert "[[ " not in text and "[[" not in text.replace("[✓]", "")
        assert "Yes" in text and "[✓]" in text

    def test_ctr_water_tests_use_caco3_ascii(self):
        keys = list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS)
        data = _ctr_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Potable Water",
                    batch_code="---",
                    quantity="1 lit",
                    parameters="Drinking Water",
                    category="water",
                    test_keys=keys,
                    **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
                ),
            ],
        )
        text = _pdf_text(_generate_ctr_pdf(data))
        assert "CaCO3" in text
        assert "\u2083" not in text
        assert "ravi@example.com" in text
        assert "Receiver's Sign" not in text
        assert "Receiver" in text
        assert "Sample Description & tests to be performed:" in text
        assert "Potable Water" in text
        assert "Sample Verification Checklist" in text
        assert "Checked for Sample Quantity" in text

    def test_delivery_mode_supports_multiple_selections(self):
        data = _ctr_request()
        data.delivery_mode = "Collect, Courier"
        text = _pdf_text(_generate_ctr_pdf(data))
        assert "Collect [✓]" in text
        assert "Courier [✓]" in text
        assert "Email/Whatsapp [ ]" in text

    def test_ctr_pdf_one_sample_has_two_pages(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 2

    def test_checklist_and_sample_on_same_page(self):
        pdf = _generate_ctr_pdf(
            _ctr_request(),
            generated_by="Priya Reception",
            generated_at="2026-09-22 12:00",
        )
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 2
        page1 = reader.pages[0].extract_text() or ""
        assert "Priya Reception" in page1
        assert "Receiver" in page1
        assert "Customer Signature" in page1
        page2 = reader.pages[1].extract_text() or ""
        assert "Checked for Sample Quantity" in page2
        assert "Tests to be performed:" in page2
        assert "Moisture" in page2

    def test_ctr_footer_has_prepared_by_and_page_count(self):
        left = _ctr_footer_left("Priya Reception", "30/07/2026 15:00", date(2026, 7, 30))
        assert "Priya Reception" in left
        assert "30/07/2026" in left
        pdf = _generate_ctr_pdf(
            _ctr_request(),
            generated_by="Priya Reception",
            generated_at="30/07/2026 15:00",
        )
        reader = PdfReader(BytesIO(pdf))
        page1 = reader.pages[0].extract_text() or ""
        assert "Prepared by:" in page1
        assert "Priya Reception" in page1
        assert "Reviewed & Issued by:" in page1
        assert "Page 1 of 2" in page1
        assert "[Control copy]" not in page1

    def test_reportlab_fallback_pdf_has_no_placeholder_logo_text(self):
        """Fallback PDF must not embed the assets/logo.png placeholder band."""
        pdf = _generate_ctr_pdf(_ctr_request(), generated_by="Reception")
        text = _pdf_text(pdf)
        assert "Replace assets" not in text

    def test_ctr_page_footer_on_last_sample_page(self):
        pdf = _generate_ctr_pdf(_ctr_request(), generated_by="Analyst Desk")
        reader = PdfReader(BytesIO(pdf))
        assert ctr_total_pages(_ctr_request()) == len(reader.pages)
        last = reader.pages[-1].extract_text() or ""
        assert "Page 2 of 2" in last
        assert "Prepared by: Analyst Desk" in last

    def test_two_samples_get_separate_pages_and_checklists(self):
        req = _ctr_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="sauce",
                    batch_code="01",
                    quantity="100gm",
                    test_keys=["moisture"],
                    **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
                ),
                SampleRow(
                    sr_no=2,
                    sample_name="honey",
                    batch_code="02",
                    quantity="200gm",
                    test_keys=["bn_protein"],
                    **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
                ),
            ]
        )
        reader = PdfReader(BytesIO(_generate_ctr_pdf(req)))
        assert len(reader.pages) == 3
        page2 = reader.pages[1].extract_text() or ""
        page3 = reader.pages[2].extract_text() or ""
        assert "sauce" in page2
        assert "honey" not in page2
        assert "honey" in page3
        assert "sauce" not in page3

    def test_generate_pdf_bytes_returns_valid_pdf_header(self):
        pdf = generate_pdf_bytes(_ctr_request())
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"
        text = _pdf_text(pdf)
        assert "Email:" in text
        assert "<b>" not in text


class TestCtrDocumentBundle:
    def test_generate_ctr_documents_prefers_docx_to_pdf(self, monkeypatch):
        fake_docx = b"PK docx"
        fake_pdf = b"%PDF-1.4 bundle"
        reportlab_called = []

        monkeypatch.setattr(ctr_pdf, "fill_docx_bytes", lambda *a, **k: fake_docx)
        monkeypatch.setattr(
            ctr_pdf,
            "convert_docx_bytes_to_pdf",
            lambda b: (fake_pdf, None),
        )
        monkeypatch.setattr(
            ctr_pdf,
            "generate_pdf_bytes",
            lambda *a, **k: reportlab_called.append(True) or fake_pdf,
        )
        monkeypatch.setattr(ctr_pdf, "suggest_docx_filename", lambda _d: "CTR.docx")
        monkeypatch.setattr(ctr_pdf, "suggest_pdf_filename", lambda _d: "CTR.pdf")

        docx, pdf, docx_name, pdf_name, err = ctr_pdf.generate_ctr_documents(
            _ctr_request(), generated_by="Priya Reception"
        )
        assert docx == fake_docx
        assert pdf == fake_pdf
        assert err is None
        assert reportlab_called == []

    def test_generate_ctr_documents_reportlab_fallback_when_no_converter(self, monkeypatch):
        fake_docx = b"PK docx"
        fake_pdf = b"%PDF-1.4 fallback"

        monkeypatch.setattr(ctr_pdf, "fill_docx_bytes", lambda *a, **k: fake_docx)
        monkeypatch.setattr(
            ctr_pdf,
            "convert_docx_bytes_to_pdf",
            lambda b: (None, "Word not available"),
        )
        monkeypatch.setattr(
            ctr_pdf,
            "generate_pdf_bytes",
            lambda *a, **k: fake_pdf,
        )
        monkeypatch.setattr(ctr_pdf, "suggest_docx_filename", lambda _d: "CTR.docx")
        monkeypatch.setattr(ctr_pdf, "suggest_pdf_filename", lambda _d: "CTR.pdf")

        docx, pdf, _, _, err = ctr_pdf.generate_ctr_documents(_ctr_request())
        assert pdf == fake_pdf
        assert err is None

    def test_generate_ctr_documents_returns_error_when_reportlab_fails(self, monkeypatch):
        fake_docx = b"PK docx"

        monkeypatch.setattr(ctr_pdf, "fill_docx_bytes", lambda *a, **k: fake_docx)
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

        docx, pdf, _, _, err = ctr_pdf.generate_ctr_documents(_ctr_request())
        assert pdf is None
        assert "Word not available" in (err or "")
        assert "ReportLab failed" in (err or "")
