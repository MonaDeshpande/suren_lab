"""Unit tests for CTR delivery mode parse/format helpers."""

from __future__ import annotations

from services.requests import (
    delivery_mode_is_selected,
    format_delivery_modes,
    parse_delivery_modes,
)


class TestParseDeliveryModes:
    def test_empty_stored_value(self):
        assert parse_delivery_modes("") == []
        assert parse_delivery_modes(None) == []

    def test_legacy_single_value(self):
        assert parse_delivery_modes("collect") == ["Collect"]
        assert parse_delivery_modes("Courier") == ["Courier"]

    def test_multiple_values_in_stable_order(self):
        assert parse_delivery_modes("Courier, Collect") == [
            "Collect",
            "Courier",
        ]
        assert parse_delivery_modes("Email/Whatsapp, Collect, Courier") == [
            "Collect",
            "Courier",
            "Email/Whatsapp",
        ]


class TestFormatDeliveryModes:
    def test_empty_selection(self):
        assert format_delivery_modes([]) == ""
        assert format_delivery_modes(None) == ""

    def test_multiple_modes_joined(self):
        assert format_delivery_modes(["Courier", "Collect"]) == "Collect, Courier"

    def test_round_trip(self):
        stored = format_delivery_modes(["Email/Whatsapp", "Collect"])
        assert parse_delivery_modes(stored) == ["Collect", "Email/Whatsapp"]


class TestDeliveryModeIsSelected:
    def test_single_legacy_value(self):
        assert delivery_mode_is_selected("collect", "Collect") is True
        assert delivery_mode_is_selected("collect", "Courier") is False

    def test_multiple_selected_values(self):
        stored = "Collect, Courier"
        assert delivery_mode_is_selected(stored, "Collect") is True
        assert delivery_mode_is_selected(stored, "Courier") is True
        assert delivery_mode_is_selected(stored, "Email/Whatsapp") is False
