"""Unit tests for admin-defined sample categories."""

from __future__ import annotations

from services.protocols.test_catalog import normalize_category
from services.sample_categories import (
    BUILTIN_SAMPLE_CATEGORIES,
    SampleCategory,
    all_sample_categories,
    category_select_options,
    is_valid_category_key,
    normalize_sample_category,
)


def test_builtin_keys_present_without_db():
    cats = all_sample_categories()
    for key in BUILTIN_SAMPLE_CATEGORIES:
        assert key in cats


def test_valid_category_key():
    assert is_valid_category_key("pharma")
    assert is_valid_category_key("feed_additives")
    assert not is_valid_category_key("P")
    assert not is_valid_category_key("Pharma!")


def test_normalize_pharma_when_listed(monkeypatch):
    monkeypatch.setattr(
        "services.sample_categories.list_categories",
        lambda active_only=True: [
            SampleCategory("food", "Food", is_builtin=True, sort_order=10),
            SampleCategory("pharma", "Pharma", is_builtin=False, sort_order=100),
        ],
    )
    assert normalize_sample_category("pharma") == "pharma"
    assert normalize_category("pharma") == "pharma"
    options = category_select_options()
    labels = [lbl for _, lbl in options]
    assert "Pharma" in labels
