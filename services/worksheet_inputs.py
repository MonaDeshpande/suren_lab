"""
services/worksheet_inputs.py
----------------------------
Composite worksheet field defaults (e.g. dish + sample weights).
"""

from __future__ import annotations

from typing import Any


def _parse_num(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_blank(value: Any) -> bool:
    return not str(value or "").strip()


def _sum_if_blank(
    target_key: str,
    inputs: dict[str, Any],
    component_keys: tuple[str, ...],
) -> dict[str, Any]:
    """Fill *target_key* with sum of components when target is empty."""
    out = dict(inputs)
    if not _is_blank(out.get(target_key)):
        return out
    parts = [_parse_num(out.get(k)) for k in component_keys]
    if any(p is None for p in parts):
        return out
    total = sum(parts)  # type: ignore[arg-type]
    out[target_key] = str(total)
    return out


def apply_composite_defaults(test_key: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Auto-fill composite weight fields from helper inputs.

    Analyst may edit the computed value; saved values are not overwritten.
    """
    out = dict(inputs or {})
    if test_key == "bn_moisture":
        out = _sum_if_blank("w1", out, ("empty_dish", "w"))
        out = _sum_if_blank("w2", out, ("after_dry",))
    elif test_key == "bn_total_ash":
        out = _sum_if_blank("before_ign", out, ("w1", "w"))
        out = _sum_if_blank("w2", out, ("after_ign",))
    return out
