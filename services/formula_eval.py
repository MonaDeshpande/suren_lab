"""
services/formula_eval.py
------------------------
Safe evaluation of Admin-defined math expressions for custom formulas.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from simpleeval import DEFAULT_OPERATORS, simple_eval

_ALLOWED_OPS = dict(DEFAULT_OPERATORS)


def _parse_number(raw: Any, field_key: str) -> float:
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"Missing value: {field_key}")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid number for {field_key}") from exc


def _field_key_map(field_keys: list[str]) -> dict[str, str]:
    """Lowercase key -> canonical field key."""
    return {k.lower(): k for k in field_keys}


def build_numeric_names(
    inputs: dict[str, Any],
    field_keys: list[str],
    *,
    required_only: bool = False,
) -> dict[str, float]:
    """Map expression variable names to numeric values from inputs."""
    key_map = _field_key_map(field_keys)
    names: dict[str, float] = {}
    for raw_key, raw_val in inputs.items():
        canonical = key_map.get(str(raw_key).lower())
        if canonical is None:
            continue
        if raw_val is None or str(raw_val).strip() == "":
            continue
        names[canonical] = _parse_number(raw_val, canonical)
        names[canonical.lower()] = names[canonical]
    if required_only:
        return names
    return names


def moisture_for_dry_basis(
    ctx: dict[str, float],
    inputs: dict[str, Any],
    moisture_input_key: Optional[str] = None,
) -> float:
    """Resolve moisture % from prior results or optional worksheet input."""
    for key in ("moisture", "bn_moisture"):
        val = ctx.get(key)
        if val is not None:
            return float(val)
    if moisture_input_key:
        key = moisture_input_key.strip()
        if key and str(inputs.get(key) or "").strip():
            return _parse_number(inputs.get(key), key)
    if str(inputs.get("moisture_pct") or "").strip():
        return _parse_number(inputs.get("moisture_pct"), "moisture_pct")
    raise ValueError("Moisture result required for dry-basis conversion")


def apply_dry_basis(wet: float, moisture: float) -> float:
    if moisture >= 100.0:
        raise ValueError("Moisture cannot be 100% or more for dry-basis conversion")
    return round(wet * 100.0 / (100.0 - moisture), 2)


def evaluate_expression(expression: str, names: dict[str, float]) -> float:
    """Evaluate a math expression with variable names bound to numbers."""
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("Formula expression is required.")
    try:
        result = simple_eval(expr, names=names, functions={}, operators=_ALLOWED_OPS)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid formula expression: {exc}") from exc
    if not isinstance(result, (int, float)):
        raise ValueError("Formula expression must return a number.")
    if result != result:  # NaN
        raise ValueError("Formula result is not a valid number.")
    return float(result)


def calculate_custom(
    expression: str,
    inputs: dict[str, Any],
    ctx: dict[str, float],
    field_keys: list[str],
    *,
    use_dry_basis: bool = False,
    moisture_input_key: Optional[str] = None,
) -> tuple[str, float]:
    """Run custom formula; optional dry-basis post-step."""
    names = build_numeric_names(inputs, field_keys)
    wet = evaluate_expression(expression, names)
    wet = round(wet, 2)
    if use_dry_basis:
        moisture = moisture_for_dry_basis(ctx, inputs, moisture_input_key)
        final = apply_dry_basis(wet, moisture)
        return f"{final}", final
    return f"{wet}", wet


def _fmt_num(value: float, places: int = 2) -> str:
    if places == 0:
        return str(int(round(value)))
    text = f"{value:.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


_VAR_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def substitute_and_format(
    expression: str,
    inputs: dict[str, Any],
    field_keys: list[str],
    result_value: str = "",
) -> str:
    """Build a worked formula line by substituting numeric inputs."""
    expr = (expression or "").strip()
    if not expr:
        return ""
    names = build_numeric_names(inputs, field_keys)
    key_map = _field_key_map(field_keys)

    def replacer(match: re.Match[str]) -> str:
        token = match.group(0)
        canonical = key_map.get(token.lower())
        if canonical and canonical in names:
            return _fmt_num(names[canonical])
        if token.lower() in names:
            return _fmt_num(names[token.lower()])
        return token

    worked = _VAR_PATTERN.sub(replacer, expr)
    ans = (result_value or "").strip()
    if ans:
        return f"{worked} = {ans}"
    try:
        val = evaluate_expression(expression, names)
        return f"{worked} = {_fmt_num(round(val, 2))}"
    except ValueError:
        return worked
