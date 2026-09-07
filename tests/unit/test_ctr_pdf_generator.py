"""Unit tests for CTR PDF generation (ReportLab)."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from pypdf import PdfReader

from services.customers import Customer
from services.pdf_generator import (
    FOOTER_RIGHT_TEXT,
    _ctr_footer_left,
    _generate_ctr_pdf,
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

    def test_ctr_pdf_renders_key_fields(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        text = _pdf_text(pdf)
        assert "Email:" in text
        assert "ravi@example.com" in text
        assert "Receiver's Sign & date" in text
        assert "Sample Description & tests to be performed:" in text
        assert "sauce" in text
        assert "Sample Verification Checklist" in text
        assert "Checked for Sample Quantity" in text

    def test_delivery_mode_supports_multiple_selections(self):
        data = _ctr_request()
        data.delivery_mode = "Collect, Courier"
        text = _pdf_text(_generate_ctr_pdf(data))
        assert "Collect [X]" in text
        assert "Courier [X]" in text
        assert "Email/Whatsapp [ ]" in text

    def test_ctr_pdf_one_sample_has_three_pages(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 3

    def test_sample_table_on_page_two_only(self):
        pdf = _generate_ctr_pdf(_ctr_request())
        reader = PdfReader(BytesIO(pdf))
        page1 = reader.pages[0].extract_text() or ""
        page2 = reader.pages[1].extract_text() or ""
        page3 = reader.pages[2].extract_text() or ""
        assert "Sample Description" not in page1
        assert "Sample Description & tests to be performed:" in page2
        assert "sauce" in page2
        assert "Tests to be performed:" in page2
        assert "Moisture" in page2
        assert "Sample Verification Checklist" in page3

    def test_ctr_footer_has_reception_and_review(self):
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
        assert "Priya Reception" in page1
        assert FOOTER_RIGHT_TEXT in page1
        assert "30/07/2026" in page1
        assert "[Control copy]" not in page1

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
        assert len(reader.pages) == 5
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
