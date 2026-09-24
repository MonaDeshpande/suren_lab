"""Unit tests for appearance_master helpers (no DB)."""

from __future__ import annotations

from services.appearance_master import _normalized_key


def test_normalized_key_strips_and_lowercases():
    assert _normalized_key("  Light Brown  ") == "light brown"
    assert _normalized_key("") == ""
