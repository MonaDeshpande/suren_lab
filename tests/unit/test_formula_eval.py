"""Unit tests for services/formula_eval.py."""

from __future__ import annotations

import pytest

from services.formula_eval import (
    apply_dry_basis,
    calculate_custom,
    evaluate_expression,
    moisture_for_dry_basis,
    substitute_and_format,
)


class TestEvaluateExpression:
    def test_basic_arithmetic(self):
        names = {"W": 10.0, "W1": 5.0, "W2": 2.0}
        result = evaluate_expression("((W1 - W2) * 100) / W", names)
        assert result == 30.0

    def test_case_insensitive_keys(self):
        names = {"w": 4.0, "w1": 3.0}
        result = evaluate_expression("w1 * 100 / w", names)
        assert result == 75.0

    def test_division_by_zero_raises(self):
        with pytest.raises(ValueError, match="Invalid formula expression"):
            evaluate_expression("10 / W", {"W": 0.0})


class TestDryBasis:
    def test_apply_dry_basis(self):
        assert apply_dry_basis(10.0, 20.0) == 12.5

    def test_moisture_from_ctx(self):
        moisture = moisture_for_dry_basis({"moisture": 15.0}, {})
        assert moisture == 15.0

    def test_calculate_with_dry_basis(self):
        display, numeric = calculate_custom(
            "((W1 - W2) * 100) / W",
            {"W": 10.0, "W1": 5.0, "W2": 2.0},
            {"moisture": 10.0},
            ["W", "W1", "W2"],
            use_dry_basis=True,
        )
        assert numeric == 33.33
        assert display == "33.33"


class TestSubstituteAndFormat:
    def test_substitute(self):
        line = substitute_and_format(
            "((W1 - W2) * 100) / W",
            {"W": 10.0, "W1": 5.0, "W2": 2.0},
            ["W", "W1", "W2"],
            "30",
        )
        assert "30" in line
        assert "=" in line
