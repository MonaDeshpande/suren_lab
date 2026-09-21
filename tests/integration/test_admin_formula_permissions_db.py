"""Integration tests for admin custom formula create/activate lifecycle."""

from __future__ import annotations

import uuid

import pytest

from services.custom_formulas import (
    CustomFormulaInput,
    activate_validated_formula,
    create_formula,
    deactivate_formula,
    invalidate_cache,
    load_custom_lab_tests,
    record_validation_trial,
)
from services.protocols.test_catalog import CATEGORY_FOOD, list_tests_for_select


def _pass_six_trials(formula_id: int) -> None:
    inputs = {"W": "10", "W1": "5", "W2": "2"}
    for _ in range(6):
        record_validation_trial(formula_id, inputs, "30")


@pytest.mark.integration
def test_admin_can_create_draft_but_not_activate_until_validated(require_db):
    invalidate_cache()
    name = f"Admin Gate {uuid.uuid4().hex[:6]}"
    rec = create_formula(
        name,
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

    with pytest.raises(ValueError, match="6 matching"):
        activate_validated_formula(rec.id)

    _pass_six_trials(rec.id)
    activated = activate_validated_formula(rec.id)
    invalidate_cache()
    assert activated.is_active and activated.is_validated
    assert activated.test_key in load_custom_lab_tests()
    keys = {k for k, _ in list_tests_for_select(CATEGORY_FOOD)}
    assert activated.test_key in keys

    deactivate_formula(activated.id)
    invalidate_cache()
    assert activated.test_key not in load_custom_lab_tests()
