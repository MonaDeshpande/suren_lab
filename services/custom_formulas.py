"""
services/custom_formulas.py
---------------------------
Admin-defined custom formulas stored in PostgreSQL, merged into runtime catalog.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.formula_eval import calculate_custom
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    InputField,
    LabTest,
    PROTOCOL_FAMILY_JAGGERY,
    PROTOCOL_FAMILY_NUTRITION,
    normalize_category,
)
from services.test_packages import (
    PACKAGE_TYPES,
    normalize_package_type,
)
from services.versions import save_version, validate_edit_reason

ENTITY_TABLE = "custom_formulas"

VALIDATION_TRIAL_COUNT = 6
MODE_CALCULATOR_FIRST = "calculator_first"
MODE_APP_FIRST = "app_first"

_KEY_SLUG_RE = re.compile(r"[^a-z0-9_]+")


@dataclass
class CustomFormulaInput:
    field_key: str
    label: str
    unit: str = ""
    required: bool = True
    field_type: str = "number"
    choices: list[str] = field(default_factory=list)
    sort_order: int = 0


@dataclass
class CustomFormula:
    id: int
    test_key: str
    name: str
    method: str
    unit: str
    category: str
    package_type: Optional[str]
    formula_display: str
    expression: str
    use_dry_basis: bool
    moisture_input_key: Optional[str]
    protocol_family: str
    is_active: bool
    is_validated: bool
    current_version_no: int
    validation_trials: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[CustomFormulaInput] = field(default_factory=list)

    @property
    def is_draft(self) -> bool:
        return not self.is_validated

    @property
    def status_label(self) -> str:
        if self.is_validated and self.is_active:
            return "Validated (active)"
        if self.is_validated and not self.is_active:
            return "Deactivated"
        return "Draft (validating)"

    @property
    def package_type_label(self) -> str:
        if not self.package_type:
            return ""
        return PACKAGE_TYPES.get(self.package_type, self.package_type)


_cache: dict[str, LabTest] | None = None


def invalidate_cache() -> None:
    global _cache  # noqa: PLW0603
    _cache = None


def _slugify(name: str) -> str:
    slug = _KEY_SLUG_RE.sub("_", (name or "").strip().lower())
    slug = slug.strip("_")
    return slug or "formula"


def _validate_inputs(inputs: list[CustomFormulaInput]) -> list[CustomFormulaInput]:
    if not inputs:
        raise ValueError("Add at least one input field.")
    seen: set[str] = set()
    cleaned: list[CustomFormulaInput] = []
    for idx, inp in enumerate(inputs):
        key = (inp.field_key or "").strip()
        label = (inp.label or "").strip()
        if not key:
            raise ValueError(f"Input field #{idx + 1}: key is required.")
        if not label:
            raise ValueError(f"Input field #{idx + 1}: label is required.")
        lower = key.lower()
        if lower in seen:
            raise ValueError(f"Duplicate input field key: {key}")
        seen.add(lower)
        cleaned.append(
            CustomFormulaInput(
                field_key=key,
                label=label,
                unit=(inp.unit or "").strip(),
                required=bool(inp.required),
                field_type=(inp.field_type or "number").strip() or "number",
                choices=list(inp.choices or []),
                sort_order=inp.sort_order if inp.sort_order else idx,
            )
        )
    return cleaned


def _validate_scope(category: str, package_type: Optional[str]) -> tuple[str, Optional[str]]:
    cat = normalize_category(category)
    ptype = normalize_package_type(package_type) if package_type else None
    if cat == CATEGORY_FOOD:
        if not ptype:
            raise ValueError("Package type is required for Food custom formulas.")
    else:
        ptype = None
    fam = PROTOCOL_FAMILY_JAGGERY
    if ptype == "nutrition_only" or ptype == "basic_nutrition" or ptype == "detailed_nutrition":
        fam = PROTOCOL_FAMILY_NUTRITION
    return cat, ptype


def _row_to_input(row: tuple) -> CustomFormulaInput:
    choices_raw = row[6] if len(row) > 6 else "[]"
    try:
        choices = json.loads(choices_raw or "[]")
        if not isinstance(choices, list):
            choices = []
    except json.JSONDecodeError:
        choices = []
    return CustomFormulaInput(
        field_key=row[1],
        label=row[2],
        unit=row[3] or "",
        required=bool(row[4]),
        field_type=row[5] or "number",
        choices=[str(c) for c in choices],
        sort_order=int(row[7]) if len(row) > 7 else 0,
    )


def answers_match(admin_answer: str, app_answer: float) -> bool:
    """True when calculator and app answers match after 2-decimal rounding."""
    try:
        admin = round(float(str(admin_answer).strip()), 2)
    except (TypeError, ValueError):
        return False
    return admin == round(float(app_answer), 2)


def trial_mode_for_index(trial_no: int) -> str:
    """Trials 1–3 calculator first; 4–6 app answer shown first."""
    if 1 <= trial_no <= 3:
        return MODE_CALCULATOR_FIRST
    if 4 <= trial_no <= 6:
        return MODE_APP_FIRST
    raise ValueError(f"Invalid trial number: {trial_no}")


def _load_validation_trials(raw: str | None) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _formula_field_keys(rec: CustomFormula) -> list[str]:
    keys = [i.field_key for i in rec.inputs]
    if rec.use_dry_basis:
        has_moisture = any(
            (i.field_key or "").lower() in ("moisture_pct", (rec.moisture_input_key or "").lower())
            for i in rec.inputs
        )
        if not has_moisture and not rec.moisture_input_key:
            keys.append("moisture_pct")
    return keys


def compute_app_answer(
    rec: CustomFormula,
    inputs: dict[str, Any],
    ctx: Optional[dict[str, float]] = None,
) -> tuple[str, float]:
    """Run the formula and return display + numeric result."""
    field_keys = _formula_field_keys(rec)
    display, numeric = calculate_custom(
        rec.expression,
        inputs,
        ctx or {},
        field_keys,
        use_dry_basis=rec.use_dry_basis,
        moisture_input_key=rec.moisture_input_key,
    )
    if numeric is None:
        raise ValueError("Formula did not produce a numeric result.")
    return display, float(numeric)


def _definition_changed(
    existing: CustomFormula,
    formula_display: str,
    expression: str,
    inputs: list[CustomFormulaInput],
    use_dry_basis: bool,
    moisture_input_key: Optional[str],
) -> bool:
    if (existing.formula_display or "").strip() != (formula_display or "").strip():
        return True
    if (existing.expression or "").strip() != (expression or "").strip():
        return True
    if bool(existing.use_dry_basis) != bool(use_dry_basis):
        return True
    if (existing.moisture_input_key or "").strip() != (moisture_input_key or "").strip():
        return True
    old_sig = sorted((i.field_key, i.label, i.unit) for i in existing.inputs)
    new_sig = sorted((i.field_key, i.label, i.unit) for i in inputs)
    return old_sig != new_sig


def _header_to_formula(row: tuple, inputs: list[CustomFormulaInput]) -> CustomFormula:
    trials_raw = row[15] if len(row) > 15 else "[]"
    return CustomFormula(
        id=int(row[0]),
        test_key=row[1],
        name=row[2],
        method=row[3] or "",
        unit=row[4] or "",
        category=row[5],
        package_type=row[6],
        formula_display=row[7],
        expression=row[8],
        use_dry_basis=bool(row[9]),
        moisture_input_key=row[10],
        protocol_family=row[11] or PROTOCOL_FAMILY_JAGGERY,
        is_active=bool(row[12]),
        is_validated=bool(row[14]) if len(row) > 14 else False,
        current_version_no=int(row[13]),
        validation_trials=_load_validation_trials(trials_raw),
        inputs=inputs,
    )


def _load_inputs(formula_id: int) -> list[CustomFormulaInput]:
    sql = """
        SELECT id, field_key, label, unit, required, field_type, choices_json, sort_order
          FROM custom_formula_inputs
         WHERE formula_id = %s
         ORDER BY sort_order, field_key
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (formula_id,))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [_row_to_input(r) for r in rows]


def get_formula(formula_id: int) -> Optional[CustomFormula]:
    sql = """
        SELECT id, test_key, name, method, unit, category, package_type,
               formula_display, expression, use_dry_basis, moisture_input_key,
               protocol_family, is_active, current_version_no,
               is_validated, validation_trials_json
          FROM custom_formulas
         WHERE id = %s
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (formula_id,))
                row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    inputs = _load_inputs(int(row[0]))
    return _header_to_formula(row, inputs)


def list_formulas(
    *,
    category: Optional[str] = None,
    package_type: Optional[str] = None,
    active_only: bool = True,
    limit: int = 500,
) -> list[CustomFormula]:
    clauses: list[str] = []
    params: list[Any] = []
    if active_only:
        clauses.append("is_active = TRUE")
        clauses.append("is_validated = TRUE")
    if category:
        clauses.append("category = %s")
        params.append(normalize_category(category))
    ptype = normalize_package_type(package_type) if package_type else None
    if ptype:
        clauses.append("package_type = %s")
        params.append(ptype)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 1000))
    sql = f"""
        SELECT id, test_key, name, method, unit, category, package_type,
               formula_display, expression, use_dry_basis, moisture_input_key,
               protocol_family, is_active, current_version_no,
               is_validated, validation_trials_json
          FROM custom_formulas
         {where}
         ORDER BY lower(name), id
         LIMIT %s
    """
    params.append(lim)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    formulas: list[CustomFormula] = []
    for row in rows:
        fid = int(row[0])
        formulas.append(_header_to_formula(row, _load_inputs(fid)))
    return formulas


def custom_formulas_for_scope(
    category: str,
    package_type: Optional[str] = None,
) -> list[CustomFormula]:
    """Active custom formulas matching a Reception sample row scope."""
    cat = normalize_category(category)
    ptype = normalize_package_type(package_type) if package_type else None
    if cat == CATEGORY_FOOD:
        if not ptype:
            return []
        return list_formulas(category=cat, package_type=ptype, active_only=True)
    return list_formulas(category=cat, active_only=True)


def formula_snapshot(formula_id: int) -> dict[str, Any]:
    rec = get_formula(formula_id)
    if rec is None:
        return {}
    return {
        "formula_id": rec.id,
        "test_key": rec.test_key,
        "name": rec.name,
        "method": rec.method,
        "unit": rec.unit,
        "category": rec.category,
        "package_type": rec.package_type,
        "formula_display": rec.formula_display,
        "expression": rec.expression,
        "use_dry_basis": rec.use_dry_basis,
        "moisture_input_key": rec.moisture_input_key,
        "protocol_family": rec.protocol_family,
        "version_no": rec.current_version_no,
        "is_active": rec.is_active,
        "is_validated": rec.is_validated,
        "validation_trials": list(rec.validation_trials),
        "inputs": [
            {
                "field_key": i.field_key,
                "label": i.label,
                "unit": i.unit,
                "required": i.required,
                "field_type": i.field_type,
                "choices": list(i.choices),
                "sort_order": i.sort_order,
            }
            for i in rec.inputs
        ],
    }


def build_lab_test(rec: CustomFormula) -> LabTest:
    """Convert a DB record into a runtime LabTest with dynamic calculator."""
    input_fields = [
        InputField(
            key=i.field_key,
            label=i.label,
            unit=i.unit,
            required=i.required,
            field_type=i.field_type,
            choices=list(i.choices),
        )
        for i in rec.inputs
    ]
    field_keys = [i.field_key for i in rec.inputs]
    if rec.use_dry_basis:
        has_moisture_field = any(
            (i.field_key or "").lower() in ("moisture_pct", rec.moisture_input_key or "")
            for i in rec.inputs
        )
        if not has_moisture_field and not rec.moisture_input_key:
            input_fields.append(
                InputField(
                    "moisture_pct",
                    "Moisture % (if not already saved)",
                    "%",
                    False,
                )
            )

    expression = rec.expression
    use_dry = rec.use_dry_basis
    moisture_key = rec.moisture_input_key
    all_keys = [f.key for f in input_fields]

    def _calculate(
        inputs: dict[str, Any],
        ctx: dict[str, float],
    ) -> tuple[str, Optional[float]]:
        display, numeric = calculate_custom(
            expression,
            inputs,
            ctx,
            all_keys,
            use_dry_basis=use_dry,
            moisture_input_key=moisture_key,
        )
        return display, numeric

    return LabTest(
        key=rec.test_key,
        name=rec.name,
        method=rec.method,
        unit=rec.unit,
        formula_display=rec.formula_display,
        inputs=input_fields,
        calculate=_calculate,
        categories=[rec.category],
        protocol_family=rec.protocol_family,
    )


def load_custom_lab_tests() -> dict[str, LabTest]:
    """Load all active custom formulas as LabTest objects (cached)."""
    global _cache  # noqa: PLW0603
    if _cache is not None:
        return _cache
    tests: dict[str, LabTest] = {}
    for rec in list_formulas(active_only=True):
        tests[rec.test_key] = build_lab_test(rec)
    _cache = tests
    return tests


def validation_state(formula_id: int) -> dict[str, Any]:
    """Current validation progress for a draft formula."""
    rec = get_formula(formula_id)
    if rec is None:
        raise ValueError(f"Custom formula #{formula_id} was not found.")
    trials = list(rec.validation_trials)
    matched = [t for t in trials if t.get("matched")]
    completed = len(matched)
    if completed >= VALIDATION_TRIAL_COUNT:
        current_trial = VALIDATION_TRIAL_COUNT
    else:
        current_trial = completed + 1
    can_activate = completed >= VALIDATION_TRIAL_COUNT and all(
        t.get("matched") for t in trials[:VALIDATION_TRIAL_COUNT]
    )
    next_mode = (
        trial_mode_for_index(current_trial)
        if completed < VALIDATION_TRIAL_COUNT
        else trial_mode_for_index(VALIDATION_TRIAL_COUNT)
    )
    return {
        "current_trial": current_trial,
        "completed_matches": completed,
        "trials": trials,
        "can_activate": can_activate,
        "next_mode": next_mode,
        "total_trials": VALIDATION_TRIAL_COUNT,
    }


def reset_validation(formula_id: int, actor=None) -> None:
    """Clear all validation trials and return formula to draft."""
    sql = """
        UPDATE custom_formulas
           SET validation_trials_json = '[]',
               is_validated = FALSE,
               is_active = FALSE,
               updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (formula_id,))
    invalidate_cache()
    log_from_user(
        actor,
        "custom_formula.validation_reset",
        ENTITY_TABLE,
        formula_id,
        details="validation trials cleared",
    )


def record_validation_trial(
    formula_id: int,
    inputs: dict[str, Any],
    admin_answer: str,
    *,
    moisture_pct: Optional[str] = None,
    actor=None,
) -> dict[str, Any]:
    """
    Check one validation trial. On match, append trial; on mismatch, reset all trials.
    """
    rec = get_formula(formula_id)
    if rec is None:
        raise ValueError(f"Custom formula #{formula_id} was not found.")
    if rec.is_validated and rec.is_active:
        raise ValueError("Formula is already validated and active.")

    trials = list(rec.validation_trials)
    if len(trials) >= VALIDATION_TRIAL_COUNT:
        raise ValueError("All 6 validation trials are already complete.")

    trial_no = len(trials) + 1
    mode = trial_mode_for_index(trial_no)
    trial_inputs = dict(inputs)
    if moisture_pct and str(moisture_pct).strip():
        trial_inputs["moisture_pct"] = moisture_pct

    ctx: dict[str, float] = {}
    if rec.use_dry_basis and str(trial_inputs.get("moisture_pct") or "").strip():
        ctx["moisture"] = float(trial_inputs["moisture_pct"])

    app_display, app_numeric = compute_app_answer(rec, trial_inputs, ctx)

    if not answers_match(admin_answer, app_numeric):
        reset_validation(formula_id, actor=actor)
        raise ValueError(
            f"Answers do not match (calculator: {admin_answer}, "
            f"app: {app_display}). All validation trials have been reset."
        )

    trial_record = {
        "trial_no": trial_no,
        "mode": mode,
        "inputs": {k: str(v) for k, v in trial_inputs.items()},
        "admin_answer": str(admin_answer).strip(),
        "app_answer": app_numeric,
        "app_display": app_display,
        "matched": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    trials.append(trial_record)

    sql = """
        UPDATE custom_formulas
           SET validation_trials_json = %s,
               updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (json.dumps(trials), formula_id))

    log_from_user(
        actor,
        "custom_formula.validation_trial",
        ENTITY_TABLE,
        formula_id,
        details=f"trial {trial_no} matched",
    )
    return validation_state(formula_id)


def activate_validated_formula(formula_id: int, actor=None) -> CustomFormula:
    """Activate formula after 6 successful validation trials."""
    state = validation_state(formula_id)
    if not state["can_activate"]:
        raise ValueError(
            f"Complete {VALIDATION_TRIAL_COUNT} matching validation trials first "
            f"({state['completed_matches']}/{VALIDATION_TRIAL_COUNT} done)."
        )
    sql = """
        UPDATE custom_formulas
           SET is_validated = TRUE,
               is_active = TRUE,
               updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (formula_id,))
    invalidate_cache()
    rec = get_formula(formula_id)
    if rec is None:
        raise RuntimeError("Formula activation succeeded but reload failed.")
    log_from_user(
        actor,
        "custom_formula.activate",
        ENTITY_TABLE,
        formula_id,
        details=rec.test_key,
    )
    return rec


def create_formula(
    name: str,
    method: str,
    unit: str,
    category: str,
    package_type: Optional[str],
    formula_display: str,
    expression: str,
    inputs: list[CustomFormulaInput],
    *,
    use_dry_basis: bool = False,
    moisture_input_key: Optional[str] = None,
    protocol_family: Optional[str] = None,
    actor=None,
) -> CustomFormula:
    """Create a new custom formula draft (not active until validated)."""
    title = (name or "").strip()
    if not title:
        raise ValueError("Test name is required.")
    display = (formula_display or "").strip()
    expr = (expression or "").strip()
    if not display:
        raise ValueError("Formula display text is required.")
    if not expr:
        raise ValueError("Formula expression is required.")
    cat, ptype = _validate_scope(category, package_type)
    cleaned_inputs = _validate_inputs(inputs)
    fam = (protocol_family or "").strip() or (
        PROTOCOL_FAMILY_NUTRITION
        if ptype in ("nutrition_only", "basic_nutrition", "detailed_nutrition")
        else PROTOCOL_FAMILY_JAGGERY
    )
    if fam not in (PROTOCOL_FAMILY_JAGGERY, PROTOCOL_FAMILY_NUTRITION):
        raise ValueError("Protocol family must be jaggery or nutrition.")

    insert_formula = """
        INSERT INTO custom_formulas (
            test_key, name, method, unit, category, package_type,
            formula_display, expression, use_dry_basis, moisture_input_key,
            protocol_family, current_version_no, is_active, is_validated,
            validation_trials_json
        )
        VALUES ('pending', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, FALSE, FALSE, '[]')
        RETURNING id, test_key, name, method, unit, category, package_type,
                  formula_display, expression, use_dry_basis, moisture_input_key,
                  protocol_family, is_active, current_version_no,
                  is_validated, validation_trials_json
    """
    insert_input = """
        INSERT INTO custom_formula_inputs (
            formula_id, field_key, label, unit, required, field_type,
            choices_json, sort_order
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    update_key = "UPDATE custom_formulas SET test_key = %s WHERE id = %s"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_formula,
                (
                    title,
                    (method or "").strip(),
                    (unit or "").strip(),
                    cat,
                    ptype,
                    display,
                    expr,
                    bool(use_dry_basis),
                    (moisture_input_key or "").strip() or None,
                    fam,
                ),
            )
            row = cur.fetchone()
            formula_id = int(row[0])
            test_key = f"custom_{formula_id}"
            cur.execute(update_key, (test_key, formula_id))
            row = (
                formula_id,
                test_key,
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
                row[15],
            )
            for order, inp in enumerate(cleaned_inputs):
                cur.execute(
                    insert_input,
                    (
                        formula_id,
                        inp.field_key,
                        inp.label,
                        inp.unit,
                        inp.required,
                        inp.field_type,
                        json.dumps(inp.choices),
                        order,
                    ),
                )

    invalidate_cache()
    log_from_user(
        actor,
        "custom_formula.create",
        ENTITY_TABLE,
        formula_id,
        details=f"{test_key} / {title}",
    )
    created = get_formula(formula_id)
    if created is None:
        raise RuntimeError("Custom formula created but reload failed.")
    return created


def update_formula(
    formula_id: int,
    name: str,
    method: str,
    unit: str,
    formula_display: str,
    expression: str,
    inputs: list[CustomFormulaInput],
    edit_reason: str,
    *,
    use_dry_basis: bool = False,
    moisture_input_key: Optional[str] = None,
    protocol_family: Optional[str] = None,
    actor=None,
) -> CustomFormula:
    """Update custom formula; archives prior state as a new version when validated."""
    existing = get_formula(formula_id)
    if existing is None:
        raise ValueError(f"Custom formula #{formula_id} was not found.")
    if existing.is_validated and not existing.is_active:
        raise ValueError("Cannot update a deactivated formula. Reactivate is not supported.")

    if existing.is_validated:
        validate_edit_reason(edit_reason)
    elif not (edit_reason or "").strip():
        edit_reason = "Draft definition update"

    title = (name or "").strip()
    if not title:
        raise ValueError("Test name is required.")
    display = (formula_display or "").strip()
    expr = (expression or "").strip()
    if not display or not expr:
        raise ValueError("Formula display and expression are required.")
    cleaned_inputs = _validate_inputs(inputs)
    fam = (protocol_family or "").strip() or existing.protocol_family
    if fam not in (PROTOCOL_FAMILY_JAGGERY, PROTOCOL_FAMILY_NUTRITION):
        raise ValueError("Protocol family must be jaggery or nutrition.")

    definition_changed = _definition_changed(
        existing,
        display,
        expr,
        cleaned_inputs,
        use_dry_basis,
        moisture_input_key,
    )

    if existing.is_validated:
        save_version(
            ENTITY_TABLE,
            formula_id,
            formula_snapshot(formula_id),
            edit_reason,
            actor=actor,
        )
        new_version = existing.current_version_no + 1
    else:
        new_version = existing.current_version_no

    update_sql = """
        UPDATE custom_formulas
           SET name = %s,
               method = %s,
               unit = %s,
               formula_display = %s,
               expression = %s,
               use_dry_basis = %s,
               moisture_input_key = %s,
               protocol_family = %s,
               current_version_no = %s,
               updated_at = NOW()
         WHERE id = %s
    """
    delete_inputs = "DELETE FROM custom_formula_inputs WHERE formula_id = %s"
    insert_input = """
        INSERT INTO custom_formula_inputs (
            formula_id, field_key, label, unit, required, field_type,
            choices_json, sort_order
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                update_sql,
                (
                    title,
                    (method or "").strip(),
                    (unit or "").strip(),
                    display,
                    expr,
                    bool(use_dry_basis),
                    (moisture_input_key or "").strip() or None,
                    fam,
                    new_version,
                    formula_id,
                ),
            )
            cur.execute(delete_inputs, (formula_id,))
            for order, inp in enumerate(cleaned_inputs):
                cur.execute(
                    insert_input,
                    (
                        formula_id,
                        inp.field_key,
                        inp.label,
                        inp.unit,
                        inp.required,
                        inp.field_type,
                        json.dumps(inp.choices),
                        order,
                    ),
                )

    if definition_changed:
        reset_validation(formula_id, actor=actor)

    invalidate_cache()
    log_from_user(
        actor,
        "custom_formula.update",
        ENTITY_TABLE,
        formula_id,
        details=f"v{new_version} / {existing.test_key}",
        edit_reason=edit_reason,
    )
    updated = get_formula(formula_id)
    if updated is None:
        raise RuntimeError("Custom formula update succeeded but reload failed.")
    return updated


def deactivate_formula(formula_id: int, actor=None) -> None:
    existing = get_formula(formula_id)
    if existing is None:
        raise ValueError(f"Custom formula #{formula_id} was not found.")
    sql = """
        UPDATE custom_formulas
           SET is_active = FALSE, updated_at = NOW()
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (formula_id,))
    invalidate_cache()
    log_from_user(
        actor,
        "custom_formula.deactivate",
        ENTITY_TABLE,
        formula_id,
        details=existing.test_key,
    )


def custom_formula_select_label(rec: CustomFormula) -> str:
    """Label for Reception multiselect."""
    parts = [rec.name]
    if rec.method:
        parts.append(f"[{rec.method}]")
    return " ".join(parts)
