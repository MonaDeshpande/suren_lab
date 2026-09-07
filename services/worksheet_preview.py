"""
services/worksheet_preview.py
------------------------------
Preview worksheet calculations without saving (Recalculate on Analyst page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from services.protocol_store import get_result_context
from services.protocols.test_catalog import (
    get_test,
    is_dry_basis_test,
    moisture_ctx_key_for,
    protein_normality_key,
    protein_normality_label,
    protein_titrant_from,
    wet_value_for_test,
)


@dataclass
class CalculationStep:
    label: str
    value: str


@dataclass
class CalculationPreview:
    steps: list[CalculationStep] = field(default_factory=list)
    final_display: str = ""
    final_numeric: Optional[float] = None
    moisture_used: Optional[float] = None
    unit: str = ""
    error: Optional[str] = None


def _moisture_used(inputs: dict[str, Any], ctx: dict[str, float], test_key: str) -> Optional[float]:
    m_key = moisture_ctx_key_for(test_key)
    if not m_key:
        return None
    raw = str(inputs.get("moisture_pct") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            return None
    val = ctx.get(m_key)
    return float(val) if val is not None else None


def preview_test_calculation(
    sample_id: int,
    test_key: str,
    inputs: dict[str, Any],
) -> CalculationPreview:
    """Run catalog formula and return step-by-step preview (no DB write)."""
    test = get_test(test_key)
    ctx = get_result_context(sample_id)
    preview = CalculationPreview(unit=test.unit or "")

    if is_dry_basis_test(test_key):
        moisture = _moisture_used(inputs, ctx, test_key)
        preview.moisture_used = moisture
        if moisture is None:
            preview.error = (
                "MOISTURE_REQUIRED:Save the Moisture test before calculating this dry-basis test."
            )
            return preview

    try:
        display, numeric = test.calculate(inputs, ctx)
    except ValueError as exc:
        preview.error = str(exc)
        return preview

    preview.final_display = display
    preview.final_numeric = numeric

    if is_dry_basis_test(test_key):
        wet = wet_value_for_test(test_key, inputs)
        if wet is not None:
            preview.steps.append(CalculationStep("Wet / intermediate (%)", f"{wet}"))
        preview.steps.append(
            CalculationStep(
                "Final on dry basis (%)",
                f"{display}",
            )
        )
        if preview.moisture_used is not None:
            preview.steps.append(
                CalculationStep("Moisture used (%)", f"{preview.moisture_used}")
            )
    elif test_key == "bn_protein":
        try:
            w = float(inputs["w"])
            titrant = protein_titrant_from(inputs)
            norm_key = protein_normality_key(titrant)
            n_titrant = float(inputs[norm_key])
            br_blank = float(inputs["br_blank"])
            br_sample = float(inputs["br_sample"])
            n_factor = float(inputs["n_factor"])
            norm_label = protein_normality_label(titrant)
            nitrogen = round(0.014 * n_titrant * (br_blank - br_sample) * 100.0 / w, 2)
            preview.steps.append(
                CalculationStep(f"Nitrogen (%) [N({norm_label})]", f"{nitrogen}")
            )
            preview.steps.append(CalculationStep("Total Protein (%)", f"{display}"))
        except (KeyError, TypeError, ValueError):
            preview.steps.append(CalculationStep("Result", f"{display}"))
    else:
        preview.steps.append(CalculationStep("Result", f"{display} {test.unit}".strip()))

    return preview
