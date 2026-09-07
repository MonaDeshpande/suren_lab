"""Unit tests for CTR intake section numbering."""

from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER
from ui.components import ctr_section_numbers


def test_new_request_food_package_first_order():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_FOOD,
        food_package_first=True,
    )
    assert sec == {
        "category": 1,
        "sample_table": 2,
        "test_selection": 3,
        "customer_lookup": 4,
        "customer_details": 5,
        "contact_persons": 6,
        "request_details": 7,
        "lab_code": 8,
        "lab_workflow": 9,
    }


def test_new_request_food_legacy_order_without_package_first():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_FOOD,
    )
    assert sec == {
        "category": 1,
        "customer_lookup": 2,
        "customer_details": 3,
        "contact_persons": 4,
        "request_details": 5,
        "lab_code": 6,
        "sample_table": 7,
        "test_selection": 8,
        "lab_workflow": 9,
    }


def test_new_request_food_includes_all_sections_in_order():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_FOOD,
    )
    assert sec == {
        "category": 1,
        "customer_lookup": 2,
        "customer_details": 3,
        "contact_persons": 4,
        "request_details": 5,
        "lab_code": 6,
        "sample_table": 7,
        "test_selection": 8,
        "lab_workflow": 9,
    }


def test_new_request_water_skips_test_selection():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_WATER,
    )
    assert sec == {
        "category": 1,
        "customer_lookup": 2,
        "customer_details": 3,
        "contact_persons": 4,
        "request_details": 5,
        "lab_code": 6,
        "sample_table": 7,
        "lab_workflow": 8,
    }
    assert "test_selection" not in sec


def test_edit_flow_food_without_customer_picker():
    sec = ctr_section_numbers(
        sample_first=False,
        include_customer_picker=False,
        filter_category=CATEGORY_FOOD,
    )
    assert sec == {
        "category": 1,
        "customer_details": 2,
        "contact_persons": 3,
        "request_details": 4,
        "lab_code": 5,
        "sample_table": 6,
        "test_selection": 7,
        "lab_workflow": 8,
    }
