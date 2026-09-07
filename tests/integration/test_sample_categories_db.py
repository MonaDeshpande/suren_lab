"""Integration tests for extra sample categories (e.g. Pharma)."""

from __future__ import annotations

import uuid

import pytest

from services.custom_formulas import (
    CustomFormulaInput,
    create_formula,
    deactivate_formula,
    invalidate_cache,
    list_formulas,
)
from services.protocols.test_catalog import normalize_category
from services.sample_categories import (
    create_category,
    list_categories,
    set_category_active,
)


@pytest.mark.integration
def test_pharma_category_normalize_and_formula(require_db):
    created = create_category("pharma", "Pharma")
    assert created.category_key == "pharma"
    assert normalize_category("pharma") == "pharma"
    labels = {c.label for c in list_categories(active_only=True)}
    assert "Pharma" in labels

    invalidate_cache()
    rec = create_formula(
        f"Pharma Assay {uuid.uuid4().hex[:8]}",
        "In-house",
        "%",
        "pharma",
        None,
        "Assay % = ((W1 - W2) * 100) / W",
        "((W1 - W2) * 100) / W",
        [
            CustomFormulaInput("W", "W", "g"),
            CustomFormulaInput("W1", "W1", "g"),
            CustomFormulaInput("W2", "W2", "g"),
        ],
    )
    assert rec.category == "pharma"
    listed = list_formulas(category="pharma", active_only=False)
    assert any(f.id == rec.id for f in listed)

    deactivate_formula(rec.id)
    invalidate_cache()
    set_category_active("pharma", is_active=False)
    inactive_keys = {c.category_key for c in list_categories(active_only=True)}
    assert "pharma" not in inactive_keys
    set_category_active("pharma", is_active=True)
