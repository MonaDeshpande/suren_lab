"""Unit tests for custom formula service helpers (no DB)."""

from __future__ import annotations

from services.custom_formulas import (
    CustomFormula,
    CustomFormulaInput,
    build_lab_test,
    custom_formula_select_label,
    invalidate_cache,
)
from services.protocols.test_catalog import CATEGORY_FOOD, missing_required_inputs


def _sample_record() -> CustomFormula:
    return CustomFormula(
        id=7,
        test_key="custom_7",
        name="Extraneous Matter (on dry basis)",
        method="FSSAI Manual",
        unit="%",
        category=CATEGORY_FOOD,
        package_type="fssai",
        formula_display="Extraneous % = (W1-W2)×100/W",
        expression="((W1 - W2) * 100) / W",
        use_dry_basis=True,
        moisture_input_key=None,
        protocol_family="jaggery",
        is_active=True,
        is_validated=True,
        current_version_no=1,
        inputs=[
            CustomFormulaInput("W", "Weight of sample", "g"),
            CustomFormulaInput("W2", "Filter paper", "g"),
            CustomFormulaInput("W1", "Filter + matter", "g"),
        ],
    )


class TestBuildLabTest:
    def test_build_and_calculate(self):
        invalidate_cache()
        rec = _sample_record()
        test = build_lab_test(rec)
        assert test.key == "custom_7"
        assert len(test.inputs) >= 3
        display, numeric = test.calculate(
            {"W": "10", "W1": "5", "W2": "2"},
            {"moisture": 10.0},
        )
        assert numeric == 33.33
        assert display == "33.33"

    def test_missing_required_inputs(self):
        test = build_lab_test(_sample_record())
        missing = missing_required_inputs(test, {"W": "10"})
        assert len(missing) >= 2

    def test_select_label(self):
        label = custom_formula_select_label(_sample_record())
        assert "Extraneous Matter" in label
        assert "FSSAI" in label
