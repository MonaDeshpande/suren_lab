"""Unit tests for mixed-category CTR intake and apply-stack sync."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_MICRO,
    CATEGORY_WATER,
    default_test_keys_for_category,
)
from ui.components import (
    INTAKE_PACKAGE_APPLY_STACK_KEY,
    _SAMPLE_EDITOR_LIVE_KEY,
    _normalize_ctr_df,
    food_intake_packages_ready,
    intake_auto_test_keys_for_row,
    sync_sample_table_from_apply_stack,
)


def test_food_package_gate_skips_water_rows(monkeypatch):
    monkeypatch.setattr(
        "services.test_packages.describe_sample_package_for_product",
        lambda name, **kw: {"status": "defined"},
    )
    rows = [
        {
            "Sr. No": 1,
            "Category": "Food",
            "Name of sample": "Jaggery",
            "Code/batch no.": "",
            "Sample qty.": "",
            "Parameters": "FSSAI",
        },
        {
            "Sr. No": 4,
            "Category": "Water",
            "Name of sample": "Potable Water",
            "Code/batch no.": "",
            "Sample qty.": "1 L",
            "Parameters": "",
        },
    ]
    ready, blocked = food_intake_packages_ready(rows, CATEGORY_FOOD)
    assert ready is True
    assert blocked == []


def test_sync_does_not_drop_manual_suffix_row():
    stack = [10, 20, 30]
    live = _normalize_ctr_df(
        pd.DataFrame(
            [
                {
                    "Sr. No": 1,
                    "Category": "Food",
                    "Name of sample": "A",
                    "Code/batch no.": "",
                    "Sample qty.": "",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                },
                {
                    "Sr. No": 2,
                    "Category": "Food",
                    "Name of sample": "B",
                    "Code/batch no.": "",
                    "Sample qty.": "",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                },
                {
                    "Sr. No": 3,
                    "Category": "Food",
                    "Name of sample": "C",
                    "Code/batch no.": "",
                    "Sample qty.": "",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                },
                {
                    "Sr. No": 4,
                    "Category": "Water",
                    "Name of sample": "Potable Water",
                    "Code/batch no.": "",
                    "Sample qty.": "500 ml",
                    "Parameters": "",
                    "_sample_id": None,
                    "_status": "pending",
                },
            ]
        )
    )
    state = {
        INTAKE_PACKAGE_APPLY_STACK_KEY: stack,
        _SAMPLE_EDITOR_LIVE_KEY: live,
        "intake_row_package_id_1": 10,
        "intake_row_package_id_2": 20,
        "intake_row_package_id_3": 30,
    }
    with patch("ui.components.st") as mock_st:
        mock_st.session_state = state
        sync_sample_table_from_apply_stack()
    result = state[_SAMPLE_EDITOR_LIVE_KEY]
    assert len(result) == 4
    assert result.iloc[3]["Category"] == "Water"


def test_intake_auto_test_keys_water_row_ignores_food_filter_context():
    cat_key_by_label = {"Food": CATEGORY_FOOD, "Water": CATEGORY_WATER}
    row = {
        "Category": "Water",
        "Name of sample": "Potable Water",
    }
    keys = intake_auto_test_keys_for_row(row, cat_key_by_label)
    expected = default_test_keys_for_category(CATEGORY_WATER)
    assert keys == expected
    assert len(keys) >= 10


def test_intake_auto_test_keys_micro_row():
    cat_key_by_label = {"Micro": CATEGORY_MICRO}
    row = {"Category": "Micro", "Name of sample": "Paneer Gravy"}
    keys = intake_auto_test_keys_for_row(row, cat_key_by_label)
    assert keys == default_test_keys_for_category(CATEGORY_MICRO)
    assert len(keys) == 6


def test_intake_auto_test_keys_food_row_empty():
    cat_key_by_label = {"Food": CATEGORY_FOOD}
    row = {"Category": "Food", "Name of sample": "Jaggery"}
    assert intake_auto_test_keys_for_row(row, cat_key_by_label) == []
