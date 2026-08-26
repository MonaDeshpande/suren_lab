"""Unit tests for worksheet input merge (primary vs recalc)."""

from __future__ import annotations

from services.input_store import (
    inputs_for_calculation,
    merge_saved_inputs,
    primary_inputs,
    recalc_inputs,
)


def test_first_save_keeps_primary_only():
    merged = merge_saved_inputs(None, {"w1": "55.1234", "w": "5.01", "w2": "54.5"})
    assert merged == {"w1": "55.1234", "w": "5.01", "w2": "54.5"}
    assert recalc_inputs(merged) == {}


def test_second_save_preserves_primary_and_adds_recalc():
    existing = {"w1": "55.1234", "w": "5.01", "w2": "54.5"}
    new_form = {"w1": "55.2", "w": "5.01", "w2": "54.48"}
    merged = merge_saved_inputs(existing, new_form)
    assert primary_inputs(merged) == existing
    assert recalc_inputs(merged) == new_form
    assert inputs_for_calculation(merged) == new_form


def test_resave_same_values_keeps_existing_recalc():
    existing = {
        "w1": "55.1234",
        "w": "5.01",
        "w2": "54.5",
        "recalc": {"w1": "55.2", "w": "5.01", "w2": "54.48"},
    }
    merged = merge_saved_inputs(existing, {"w1": "55.1234", "w": "5.01", "w2": "54.5"})
    assert recalc_inputs(merged) == existing["recalc"]
