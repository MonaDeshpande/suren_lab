"""Unit tests for CTR mark and display normalization."""

from __future__ import annotations

from services.ctr_symbols import (
    normalize_ctr_display_text,
    yes_no_option_line,
)


def test_yes_no_option_line_single_brackets():
    line = yes_no_option_line(True)
    assert "[[ " not in line
    assert "[✓]" in line
    assert "[ ]" in line


def test_normalize_ctr_display_text_subscript_three():
    assert normalize_ctr_display_text("Total Alkalinity as CaCO\u2083") == (
        "Total Alkalinity as CaCO3"
    )
