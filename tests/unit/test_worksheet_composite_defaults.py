"""Unit tests for composite worksheet input defaults."""

from __future__ import annotations

from services.worksheet_inputs import apply_composite_defaults


def test_bn_moisture_w1_from_dish_and_sample():
    result = apply_composite_defaults(
        "bn_moisture",
        {"empty_dish": "10", "w": "5"},
    )
    assert result["w1"] == "15.0"


def test_bn_moisture_preserves_existing_w1():
    result = apply_composite_defaults(
        "bn_moisture",
        {"empty_dish": "10", "w": "5", "w1": "16"},
    )
    assert result["w1"] == "16"


def test_bn_total_ash_before_ign_from_crucible_and_sample():
    result = apply_composite_defaults(
        "bn_total_ash",
        {"w1": "12", "w": "3"},
    )
    assert result["before_ign"] == "15.0"
