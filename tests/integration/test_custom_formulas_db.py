"""Integration tests for custom formula validation (requires PostgreSQL)."""

from __future__ import annotations

import pytest

from services.custom_formulas import (
    CustomFormulaInput,
    activate_validated_formula,
    create_formula,
    custom_formulas_for_scope,
    deactivate_formula,
    get_formula,
    invalidate_cache,
    load_custom_lab_tests,
    record_validation_trial,
    reset_validation,
    validation_state,
)
from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER, get_test


def _pass_six_trials(formula_id: int, admin_answer: str = "30") -> None:
    """Six trials with inputs that yield 30 for ((W1-W2)*100)/W with W=10,W1=5,W2=2."""
    inputs = {"W": "10", "W1": "5", "W2": "2"}
    for _ in range(6):
        record_validation_trial(formula_id, inputs, admin_answer)


@pytest.mark.integration
def test_draft_not_in_catalog_until_activated(require_db):
    invalidate_cache()
    rec = create_formula(
        "Validation Gate Test",
        "Test",
        "%",
        CATEGORY_FOOD,
        "fssai",
        "Test % = ((W1 - W2) * 100) / W",
        "((W1 - W2) * 100) / W",
        [
            CustomFormulaInput("W", "W", "g"),
            CustomFormulaInput("W1", "W1", "g"),
            CustomFormulaInput("W2", "W2", "g"),
        ],
    )
    assert not rec.is_validated
    assert not rec.is_active
    assert rec.test_key not in load_custom_lab_tests()
    assert not any(f.id == rec.id for f in custom_formulas_for_scope(CATEGORY_FOOD, "fssai"))

    _pass_six_trials(rec.id)
    state = validation_state(rec.id)
    assert state["can_activate"]

    activated = activate_validated_formula(rec.id)
    invalidate_cache()
    assert activated.is_validated and activated.is_active
    assert activated.test_key in load_custom_lab_tests()
    assert any(f.id == rec.id for f in custom_formulas_for_scope(CATEGORY_FOOD, "fssai"))

    test = get_test(activated.test_key)
    display, numeric = test.calculate({"W": "10", "W1": "5", "W2": "2"}, {})
    assert numeric == 30.0

    deactivate_formula(rec.id)
    invalidate_cache()


@pytest.mark.integration
def test_mismatch_resets_all_trials(require_db):
    invalidate_cache()
    rec = create_formula(
        "Mismatch Reset Test",
        "",
        "%",
        CATEGORY_WATER,
        None,
        "Pct = ((W1 - W2) * 100) / W",
        "((W1 - W2) * 100) / W",
        [
            CustomFormulaInput("W", "W", "g"),
            CustomFormulaInput("W1", "W1", "g"),
            CustomFormulaInput("W2", "W2", "g"),
        ],
    )
    inputs = {"W": "10", "W1": "5", "W2": "2"}
    record_validation_trial(rec.id, inputs, "30")
    assert validation_state(rec.id)["completed_matches"] == 1

    with pytest.raises(ValueError, match="reset"):
        record_validation_trial(rec.id, inputs, "99")

    assert validation_state(rec.id)["completed_matches"] == 0
    deactivate_formula(rec.id)


@pytest.mark.integration
def test_activate_blocked_until_six_trials(require_db):
    invalidate_cache()
    rec = create_formula(
        "Activate Block Test",
        "",
        "%",
        CATEGORY_WATER,
        None,
        "X = W",
        "W",
        [CustomFormulaInput("W", "W", "g")],
    )
    with pytest.raises(ValueError, match="6 matching"):
        activate_validated_formula(rec.id)

    record_validation_trial(rec.id, {"W": "10"}, "10")
    with pytest.raises(ValueError, match="6 matching"):
        activate_validated_formula(rec.id)

    reset_validation(rec.id)
    deactivate_formula(rec.id)
