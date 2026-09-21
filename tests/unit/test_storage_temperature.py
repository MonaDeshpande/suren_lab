"""Unit tests for CTR storage temperature select/save helpers."""

from __future__ import annotations

from services.requests import (
    STORAGE_TEMPERATURE_OTHER,
    format_storage_temperature_celsius,
    storage_temperature_for_save,
    storage_temperature_select_value,
)


class TestStorageTemperatureSelectValue:
    def test_empty_stored_value(self):
        assert storage_temperature_select_value("") == ""
        assert storage_temperature_select_value(None) == ""

    def test_canonical_option_round_trip(self):
        assert storage_temperature_select_value("Room Temp") == "Room Temp"
        assert storage_temperature_select_value("2°C to 8°C") == "2°C to 8°C"

    def test_legacy_custom_maps_to_other(self):
        assert storage_temperature_select_value("Ambient / 2–8 °C") == (
            STORAGE_TEMPERATURE_OTHER
        )


class TestStorageTemperatureForSave:
    def test_canonical_option_saved_as_is(self):
        assert storage_temperature_for_save("4°C", "") == "4°C"

    def test_other_uses_custom_text(self):
        assert storage_temperature_for_save(
            STORAGE_TEMPERATURE_OTHER,
            "Frozen (-20°C)",
        ) == "Frozen (-20°C)"

    def test_empty_selection(self):
        assert storage_temperature_for_save("", "ignored") == ""

    def test_other_trims_whitespace(self):
        assert storage_temperature_for_save(STORAGE_TEMPERATURE_OTHER, "  Ice  ") == (
            "Ice°C"
        )


class TestFormatStorageTemperatureCelsius:
    def test_numeric_appends_degree_c(self):
        assert format_storage_temperature_celsius("4") == "4°C"

    def test_existing_degree_c_unchanged(self):
        assert format_storage_temperature_celsius("2°C to 8°C") == "2°C to 8°C"

    def test_no_duplicate_suffix(self):
        assert format_storage_temperature_celsius("4°C") == "4°C"
        assert "°C°C" not in format_storage_temperature_celsius("4°C")

    def test_text_without_unit_gets_suffix(self):
        assert format_storage_temperature_celsius("Frozen") == "Frozen°C"

    def test_for_save_canonical_option_gets_formatted(self):
        assert storage_temperature_for_save("4°C", "") == "4°C"
