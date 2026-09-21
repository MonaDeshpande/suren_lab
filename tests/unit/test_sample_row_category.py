"""Unit tests for per-row sample category on CTR intake."""

from __future__ import annotations

from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER, normalize_category
from services.requests import SampleRow, TestRequestData, _sample_request_details_tuple
from services.customers import Customer


def _customer() -> Customer:
    return Customer(
        customer_name="Test Co",
        address="",
        contact_person="",
        contact_number="",
        email="",
        gst_number="29TEST0000A1Z5",
    )


def test_sample_row_stores_per_row_category():
    food = SampleRow(sr_no=1, sample_name="Jaggery", category="food")
    water = SampleRow(sr_no=2, sample_name="Water", category="water")
    assert normalize_category(food.category) == CATEGORY_FOOD
    assert normalize_category(water.category) == CATEGORY_WATER


def test_mixed_categories_in_one_request():
    data = TestRequestData(
        customer=_customer(),
        samples=[
            SampleRow(sr_no=1, sample_name="A", category="food"),
            SampleRow(sr_no=2, sample_name="B", category="water"),
        ],
    )
    cats = {normalize_category(s.category) for s in data.samples}
    assert cats == {CATEGORY_FOOD, CATEGORY_WATER}


def test_save_tuple_includes_per_row_request_fields():
    sample = SampleRow(
        sr_no=1,
        category="water",
        storage_temperature="4°C",
        sampling_by_lab=True,
        decision_rule=False,
        service_type="Urgent",
        delivery_mode="Collect",
        test_method_spec="IS 10500",
    )
    assert _sample_request_details_tuple(sample) == (
        "4°C",
        True,
        False,
        "Urgent",
        "Collect",
        "IS 10500",
    )
