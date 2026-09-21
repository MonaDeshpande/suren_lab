"""Unit tests for protocol analysis date range helpers."""

from __future__ import annotations

from datetime import date

from services.protocol_store import (
    format_analysis_date_range,
    validate_analysis_date_range,
)


def test_validate_rejects_end_before_start():
    errors = validate_analysis_date_range(
        date(2026, 7, 10),
        date(2026, 7, 9),
    )
    assert errors == ["Analysis Date To must be on or after Analysis Date From."]


def test_validate_accepts_valid_range():
    assert validate_analysis_date_range(date(2026, 7, 1), date(2026, 7, 5)) == []


def test_validate_allows_partial_dates():
    assert validate_analysis_date_range(date(2026, 7, 1), None) == []
    assert validate_analysis_date_range(None, date(2026, 7, 5)) == []


def test_format_single_date():
    assert format_analysis_date_range(
        date(2026, 7, 15),
        date(2026, 7, 15),
    ) == "15/07/2026"


def test_format_range():
    assert format_analysis_date_range(
        date(2026, 7, 1),
        date(2026, 7, 10),
    ) == "01/07/2026 to 10/07/2026"


def test_format_legacy_single_fallback():
    assert format_analysis_date_range(
        None,
        None,
        legacy_single=date(2026, 6, 20),
    ) == "20/06/2026"
