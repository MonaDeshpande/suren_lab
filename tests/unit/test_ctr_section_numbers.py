"""Unit tests for CTR intake section numbering."""

from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER
from ui.components import ctr_section_numbers


def test_new_request_food_includes_all_sections_in_order():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_FOOD,
    )
    assert sec == {
        "category": 1,
        "sample_table": 2,
        "test_selection": 3,
        "lab_workflow": 4,
        "customer_lookup": 5,
        "customer_details": 6,
        "contact_persons": 7,
        "request_details": 8,
    }


def test_new_request_water_skips_test_selection():
    sec = ctr_section_numbers(
        sample_first=True,
        include_customer_picker=True,
        filter_category=CATEGORY_WATER,
    )
    assert sec == {
        "category": 1,
        "sample_table": 2,
        "lab_workflow": 3,
        "customer_lookup": 4,
        "customer_details": 5,
        "contact_persons": 6,
        "request_details": 7,
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
        "sample_table": 5,
        "test_selection": 6,
        "lab_workflow": 7,
    }
