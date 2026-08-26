"""
services/input_store.py
-----------------------
Merge primary and recalculation worksheet inputs for protocol column 1 / 2.
"""

from __future__ import annotations

from typing import Any

RECALC_KEY = "recalc"


def primary_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    """Top-level worksheet values excluding the recalc bucket."""
    if not inputs:
        return {}
    return {k: v for k, v in inputs.items() if k != RECALC_KEY}


def recalc_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    """Nested recalculation values when the analyst re-saved with new readings."""
    if not inputs:
        return {}
    nested = inputs.get(RECALC_KEY)
    if not isinstance(nested, dict):
        return {}
    return dict(nested)


def _norm_inputs(values: dict[str, Any]) -> dict[str, str]:
    return {k: str(v).strip() for k, v in values.items() if k != RECALC_KEY}


def inputs_for_calculation(stored: dict[str, Any]) -> dict[str, Any]:
    """Values used for the latest saved result (recalc when present)."""
    rec = recalc_inputs(stored)
    if rec:
        return rec
    return primary_inputs(stored)


def merge_saved_inputs(
    existing: dict[str, Any] | None,
    new_form: dict[str, Any],
) -> dict[str, Any]:
    """
    Preserve first-save readings at top level; store later edits under ``recalc``.
    """
    new_clean = primary_inputs(new_form)
    if not existing:
        return new_clean

    primary = primary_inputs(existing)
    if _norm_inputs(new_clean) == _norm_inputs(primary):
        out = dict(primary)
        old_recalc = recalc_inputs(existing)
        if old_recalc:
            out[RECALC_KEY] = old_recalc
        return out

    return {**primary, RECALC_KEY: new_clean}
