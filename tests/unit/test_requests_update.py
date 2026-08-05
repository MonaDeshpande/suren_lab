"""Unit tests for test request update rules (no DB)."""

from __future__ import annotations

from services.requests import SampleRow, TestRequestData, ctr_parameters_display
from services.customers import Customer
from services.protocols.test_catalog import CATEGORY_WATER


class TestSampleRowEditGuards:
    def test_sample_row_carries_id_and_status(self):
        row = SampleRow(
            id=5,
            sr_no=1,
            sample_name="Jaggery",
            sample_code="SLS-260721-0001",
            status="in_progress",
        )
        assert row.id == 5
        assert row.status == "in_progress"

    def test_request_data_request_id(self):
        customer = Customer(
            customer_name="Acme",
            address="Addr",
            contact_person="Ravi",
            contact_number="1",
            email="a@b.com",
            gst_number="27AAAAA0000A1Z5",
        )
        data = TestRequestData(customer=customer, request_id=99)
        assert data.request_id == 99


class TestCtrParametersDisplay:
    def test_food_uses_package_type_label(self):
        row = SampleRow(
            sr_no=1,
            sample_name="Jaggery",
            category="food",
            parameters="Jaggery — FSSAI — tests to be conducted (Moisture)",
            package_type="fssai",
        )
        assert ctr_parameters_display(row) == "FSSAI"

    def test_food_legacy_parameters_label(self):
        row = SampleRow(
            sr_no=1,
            sample_name="Jaggery",
            category="food",
            parameters="FSSAI",
        )
        assert ctr_parameters_display(row) == "FSSAI"

    def test_water_empty_parameters(self):
        row = SampleRow(
            sr_no=1,
            sample_name="Tap water",
            category=CATEGORY_WATER,
            parameters="pH, TDS, Chloride",
        )
        assert ctr_parameters_display(row) == ""

    def test_other_category_uses_free_text(self):
        row = SampleRow(
            sr_no=1,
            sample_name="Feed sample",
            category="cattle_feed_fertilizer",
            parameters="Custom test list",
        )
        assert ctr_parameters_display(row) == "Custom test list"
