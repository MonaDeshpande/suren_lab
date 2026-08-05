"""Unit tests for CTR PDF generation (ReportLab)."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from pypdf import PdfReader

from services.customers import Customer
from services.pdf_generator import FOOTER_TEXT, _generate_ctr_pdf, generate_pdf_bytes
from services.requests import SampleRow, TestRequestData


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
        number_of_samples=1,
        sampling_by_lab=True,
        decision_rule=True,
        service_type="regular",
        delivery_mode="collect",
        samples=[
            SampleRow(
                sr_no=1,
                sample_name="sauce",
                batch_code="01",
                quantity="100gm",
                parameters="FSSAI",
                package_type="fssai",
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

    def test_ctr_pdf_renders_key_fields(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        text = _pdf_text(pdf)
        assert "Email:" in text
        assert "ravi@example.com" in text
        assert "Receiver's Sign & date" in text
        assert "Sample Description & tests to be performed:" in text
        assert "sauce" in text
        assert "FSSAI" in text

    def test_ctr_pdf_is_two_pages(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 2

    def test_sample_table_on_page_two(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        reader = PdfReader(BytesIO(pdf))
        page1 = reader.pages[0].extract_text() or ""
        page2 = reader.pages[1].extract_text() or ""
        assert "Sample Description" not in page1
        assert "Sample Description & tests to be performed:" in page2
        assert "sauce" in page2
        assert "FSSAI" in page2
        assert FOOTER_TEXT in page1 or "[Control copy]" in page1

    def test_generate_pdf_bytes_returns_valid_pdf_header(self):
        pdf = generate_pdf_bytes(_ctr_request())
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"
        text = _pdf_text(pdf)
        assert "Email:" in text
        assert "<b>" not in text
