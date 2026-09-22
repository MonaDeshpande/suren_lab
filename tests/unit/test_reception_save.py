"""Smoke tests for Reception save / CTR download helpers."""

from __future__ import annotations

import ui.reception_save as reception_save


def test_reception_save_imports_category_food():
    assert reception_save.CATEGORY_FOOD == "food"
    assert reception_save.CATEGORY_WATER == "water"


def test_food_category_branch_uses_imported_constant():
    """render_ctr_downloads compares food samples with CATEGORY_FOOD (was NameError)."""
    from services.protocols.test_catalog import CATEGORY_FOOD

    assert reception_save.CATEGORY_FOOD is CATEGORY_FOOD
