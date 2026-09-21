"""Integration tests for food catalog visibility in test packages."""

from __future__ import annotations

import uuid

import pytest

from services.custom_formulas import (
    CustomFormulaInput,
    activate_validated_formula,
    create_formula,
    deactivate_formula,
    invalidate_cache,
    record_validation_trial,
)
from services.protocols.test_catalog import CATEGORY_FOOD, FOOD_TEST_KEYS, list_tests_for_select
from services.test_packages import (
    PACKAGE_TYPE_FSSAI,
    create_package,
    resolve_package_tests,
)
from ui.components import _intake_test_label_options


def _pass_six_trials(formula_id: int) -> None:
    inputs = {"W": "10", "W1": "5", "W2": "2"}
    for _ in range(6):
        record_validation_trial(formula_id, inputs, "30")


@pytest.mark.integration
def test_food_catalog_has_at_least_twenty_one_tests():
    options = list_tests_for_select(CATEGORY_FOOD)
    assert len(options) >= 21
    labels = [lbl for _, lbl in options]
    assert all("bn_" not in lbl for lbl in labels)


@pytest.mark.integration
def test_activated_custom_formula_visible_in_package_and_intake(require_db):
    invalidate_cache()
    suffix = uuid.uuid4().hex[:6]
    rec = create_formula(
        f"Pkg Visibility {suffix}",
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
    _pass_six_trials(rec.id)
    activated = activate_validated_formula(rec.id)
    invalidate_cache()

    catalog_keys = {k for k, _ in list_tests_for_select(CATEGORY_FOOD)}
    assert activated.test_key in catalog_keys

    pkg = create_package(
        f"QA Mix {suffix}",
        PACKAGE_TYPE_FSSAI,
        ["moisture", "bn_protein"],
        [activated.test_key],
    )
    resolved = resolve_package_tests(pkg.sample_product_name, PACKAGE_TYPE_FSSAI)
    assert resolved is not None
    assert "moisture" in resolved.test_keys_with_logo
    assert activated.test_key in resolved.test_keys_without_logo

    labels, label_map = _intake_test_label_options(list(resolved.test_keys_with_logo))
    assert label_map[labels[0]] == "moisture"

    deactivate_formula(activated.id)
    invalidate_cache()


@pytest.mark.integration
def test_package_accepts_mixed_jaggery_and_nutrition_keys(require_db):
    suffix = uuid.uuid4().hex[:6]
    mixed = ["moisture", "bn_protein"]
    pkg = create_package(
        f"QA Mixed {suffix}",
        PACKAGE_TYPE_FSSAI,
        mixed,
        [],
    )
    assert set(pkg.test_keys_with_logo) == set(mixed)
    assert all(k in FOOD_TEST_KEYS for k in mixed)
