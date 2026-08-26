"""Unit tests for shared numeric formatting helpers."""

from __future__ import annotations

import pytest

from services.number_format import (
    decimal_places,
    format_final_number,
    format_input_number,
    format_report_number,
    strip_analyst_label_suffix,
    validate_max_decimals,
)


def test_decimal_places_counts_fraction_digits():
    assert decimal_places("55.1234") == 4
    assert decimal_places("6") == 0
    assert decimal_places("9.50") == 2


def test_validate_max_decimals_rejects_fifth_place():
    validate_max_decimals("55.1234", 4)
    with pytest.raises(ValueError):
        validate_max_decimals("55.12345", 4)


def test_format_input_number_trims_trailing_zeros():
    assert format_input_number(6.0) == "6"
    assert format_input_number("55.1234") == "55.1234"
    assert format_input_number("5.0100") == "5.01"


def test_format_final_number_always_two_decimals():
    assert format_final_number(6) == "6.00"
    assert format_final_number(1.19) == "1.19"
    assert format_final_number(7.3) == "7.30"


def test_format_report_number_pads_under_ten():
    assert format_report_number("1.19") == "01.19"
    assert format_report_number("9.5") == "09.50"
    assert format_report_number("6.00") == "06.00"
    assert format_report_number("12.34") == "12.34"
    assert format_report_number("Absent") == "Absent"


def test_strip_analyst_label_suffix():
    assert strip_analyst_label_suffix("Priya Sharma (psharma)") == "Priya Sharma"
    assert strip_analyst_label_suffix("Priya Sharma") == "Priya Sharma"
