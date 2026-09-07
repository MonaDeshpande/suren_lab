"""
ui/custom_formulas_panel.py
---------------------------
Admin UI for creating and managing custom formulas with 6-trial validation.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from services.custom_formulas import (
    MODE_APP_FIRST,
    MODE_CALCULATOR_FIRST,
    CustomFormula,
    CustomFormulaInput,
    activate_validated_formula,
    compute_app_answer,
    create_formula,
    deactivate_formula,
    get_formula,
    list_formulas,
    record_validation_trial,
    update_formula,
    validation_state,
)
from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    PROTOCOL_FAMILY_JAGGERY,
    PROTOCOL_FAMILY_NUTRITION,
)
from services.sample_categories import all_sample_categories, category_select_options
from services.test_packages import PACKAGE_TYPE_LABELS, LABEL_TO_PACKAGE_TYPE
from services.versions import list_versions
from ui.components import edit_reason_field, render_section_title, require_edit_reason


def _default_input_rows() -> list[dict[str, Any]]:
    return [
        {"field_key": "W", "label": "Weight of sample taken (W)", "unit": "g"},
        {"field_key": "W2", "label": "Weight of Filter Paper (W2)", "unit": "g"},
        {"field_key": "W1", "label": "Weight of Filter Paper + Dry matter (W1)", "unit": "g"},
    ]


def _read_input_rows(prefix: str, count: int) -> list[CustomFormulaInput]:
    rows: list[CustomFormulaInput] = []
    for i in range(count):
        key = st.session_state.get(f"{prefix}_key_{i}", "")
        label = st.session_state.get(f"{prefix}_label_{i}", "")
        unit = st.session_state.get(f"{prefix}_unit_{i}", "")
        if not str(key).strip() and not str(label).strip():
            continue
        rows.append(
            CustomFormulaInput(
                field_key=str(key).strip(),
                label=str(label).strip(),
                unit=str(unit or "").strip(),
                required=True,
                field_type="number",
                sort_order=i,
            )
        )
    return rows


def _render_input_editor(prefix: str, rows: list[dict[str, Any]], count_key: str) -> int:
    count = st.session_state.get(count_key, len(rows))
    st.caption("Input fields (keys become variables in the expression, e.g. W, W1, W2).")
    for i in range(count):
        c1, c2, c3 = st.columns([2, 4, 2])
        with c1:
            st.text_input(
                f"Key {i + 1}",
                value=rows[i].get("field_key", "") if i < len(rows) else "",
                key=f"{prefix}_key_{i}",
            )
        with c2:
            st.text_input(
                f"Label {i + 1}",
                value=rows[i].get("label", "") if i < len(rows) else "",
                key=f"{prefix}_label_{i}",
            )
        with c3:
            st.text_input(
                f"Unit {i + 1}",
                value=rows[i].get("unit", "") if i < len(rows) else "",
                key=f"{prefix}_unit_{i}",
            )
    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("Add input field", key=f"{prefix}_add_field"):
            st.session_state[count_key] = count + 1
            st.rerun()
    with bc2:
        if count > 1 and st.button("Remove last field", key=f"{prefix}_remove_field"):
            st.session_state[count_key] = max(1, count - 1)
            st.rerun()
    return count


def _mode_label(mode: str) -> str:
    if mode == MODE_CALCULATOR_FIRST:
        return "Calculator first — enter your calculator answer, then compare with the app"
    return "App first — app shows the answer; enter your calculator result to verify"


def _render_validation_wizard(rec: CustomFormula, actor, key_prefix: str) -> None:
    """Six-trial validation wizard before a formula can go live."""
    st.markdown("### Validation (6 trials required)")
    st.caption(
        "Trials 1–3: fill inputs and enter your **calculator answer** first. "
        "Trials 4–6: app shows the answer first; enter your calculator result. "
        "Any mismatch resets all trials."
    )

    state = validation_state(rec.id)
    completed = state["completed_matches"]
    total = state["total_trials"]
    st.progress(completed / total, text=f"{completed}/{total} trials matched")

    if state["can_activate"]:
        st.success("All 6 trials matched. You can activate this formula.")
        if st.button("Activate formula", type="primary", key=f"{key_prefix}_activate"):
            try:
                activated = activate_validated_formula(rec.id, actor=actor)
                st.success(f"**{activated.name}** is now live at Reception and Analyst.")
                if key_prefix == "cf_create":
                    st.session_state.pop("cf_draft_formula_id", None)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        return

    current = state["current_trial"]
    mode = state["next_mode"]
    st.markdown(f"**Trial {current}/{total}** — {_mode_label(mode)}")

    trial_inputs: dict[str, str] = {}
    for inp in rec.inputs:
        trial_inputs[inp.field_key] = st.text_input(
            f"{inp.label} ({inp.field_key})",
            key=f"{key_prefix}_trial_{rec.id}_{current}_{inp.field_key}",
        )

    moisture_pct = ""
    if rec.use_dry_basis:
        moisture_pct = st.text_input(
            "Moisture % (for dry-basis)",
            key=f"{key_prefix}_trial_{rec.id}_{current}_moisture",
        )

    app_display = ""
    app_numeric: float | None = None
    inputs_ready = all(str(v).strip() for v in trial_inputs.values())
    if rec.use_dry_basis:
        inputs_ready = inputs_ready and str(moisture_pct).strip()

    if mode == MODE_APP_FIRST and inputs_ready:
        try:
            app_display, app_numeric = compute_app_answer(rec, trial_inputs)
            st.info(f"**App answer:** {app_display} {rec.unit or ''}".strip())
        except Exception as exc:  # noqa: BLE001
            st.caption(f"App preview error: {exc}")

    admin_answer = st.text_input(
        "Your calculator answer *",
        key=f"{key_prefix}_trial_{rec.id}_{current}_admin",
    )

    if mode == MODE_CALCULATOR_FIRST:
        if st.button("Check match", key=f"{key_prefix}_check_{rec.id}_{current}"):
            try:
                record_validation_trial(
                    rec.id,
                    trial_inputs,
                    admin_answer,
                    moisture_pct=moisture_pct or None,
                    actor=actor,
                )
                st.success(f"Trial {current} matched.")
                st.checkbox("Match", value=True, disabled=True, key=f"{key_prefix}_match_ok_{rec.id}_{current}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        if inputs_ready and admin_answer.strip():
            try:
                app_display, app_numeric = compute_app_answer(rec, trial_inputs)
                st.caption(f"App answer: **{app_display}** {rec.unit or ''}".strip())
            except Exception as exc:  # noqa: BLE001
                st.caption(f"App preview error: {exc}")
    else:
        if st.button("Check match", key=f"{key_prefix}_check_{rec.id}_{current}"):
            try:
                record_validation_trial(
                    rec.id,
                    trial_inputs,
                    admin_answer,
                    moisture_pct=moisture_pct or None,
                    actor=actor,
                )
                st.success(f"Trial {current} matched.")
                st.checkbox("Match", value=True, disabled=True, key=f"{key_prefix}_match_ok_{rec.id}_{current}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    trials = state["trials"]
    if trials:
        with st.expander("Completed trials", expanded=False):
            for t in trials:
                match_icon = "✓" if t.get("matched") else "✗"
                st.markdown(
                    f"**Trial {t.get('trial_no')}** ({t.get('mode')}) {match_icon} — "
                    f"calc: {t.get('admin_answer')} · app: {t.get('app_display')}"
                )


def render_custom_formulas_panel(actor) -> None:
    """Admin panel for custom formula CRUD + validation."""
    render_section_title(
        "Custom formulas",
        "Define tests, pass 6 validation trials, then activate for Reception and Analyst.",
    )

    tab_create, tab_manage = st.tabs(["Create formula", "Manage formulas"])

    with tab_create:
        _render_create_tab(actor)

    with tab_manage:
        _render_manage_tab(actor)


def _render_create_tab(actor) -> None:
    draft_id = st.session_state.get("cf_draft_formula_id")
    if draft_id:
        rec = get_formula(int(draft_id))
        if rec is None or rec.is_validated:
            st.session_state.pop("cf_draft_formula_id", None)
            st.rerun()
        else:
            st.info(f"Draft: **{rec.name}** (`{rec.test_key}`) — complete validation to activate.")
            _render_validation_wizard(rec, actor, "cf_create")
            if st.button("Discard draft and start over", key="cf_discard_draft"):
                st.session_state.pop("cf_draft_formula_id", None)
                st.rerun()
            return

    cat_options = category_select_options()
    cat_labels = [lbl for _, lbl in cat_options]
    label_to_cat = {lbl: k for k, lbl in cat_options}

    c1, c2 = st.columns(2)
    with c1:
        cat_label = st.selectbox("Sample category *", options=cat_labels, key="cf_new_cat")
        category = label_to_cat[cat_label]
    with c2:
        if category == CATEGORY_FOOD:
            type_label = st.selectbox(
                "Package type *",
                options=PACKAGE_TYPE_LABELS,
                key="cf_new_pkg_type",
            )
            package_type = LABEL_TO_PACKAGE_TYPE[type_label]
        else:
            st.caption("Package type applies to Food only.")
            package_type = None

    c3, c4, c5 = st.columns(3)
    with c3:
        name = st.text_input(
            "Test name *",
            key="cf_new_name",
            placeholder="Extraneous Matter (on dry basis)",
        )
    with c4:
        method = st.text_input("Method / reference", key="cf_new_method")
    with c5:
        unit = st.text_input("Result unit", key="cf_new_unit", placeholder="%")

    formula_display = st.text_input(
        "Formula display (shown to analyst) *",
        key="cf_new_display",
        placeholder="Extraneous Matter (%) = ((W1 - W2) × 100) / W",
    )
    expression = st.text_input(
        "Math expression *",
        key="cf_new_expr",
        placeholder="((W1 - W2) * 100) / W",
        help="Use input field keys as variables. Operators: +, -, *, /, parentheses.",
    )

    if category == CATEGORY_FOOD:
        fam_label = st.selectbox(
            "Protocol family",
            options=["Jaggery", "Basic Nutrition"],
            key="cf_new_family",
        )
        protocol_family = (
            PROTOCOL_FAMILY_NUTRITION if fam_label == "Basic Nutrition" else PROTOCOL_FAMILY_JAGGERY
        )
    else:
        protocol_family = PROTOCOL_FAMILY_JAGGERY

    use_dry = st.checkbox(
        "Apply dry-basis conversion (result × 100 / (100 − moisture))",
        key="cf_new_dry",
    )
    moisture_key = ""
    if use_dry:
        moisture_key = st.text_input(
            "Moisture input field key (optional)",
            key="cf_new_moisture_key",
            help="Leave blank to use saved moisture / bn_moisture or moisture_pct during validation.",
        )

    if "cf_new_field_count" not in st.session_state:
        st.session_state["cf_new_field_count"] = 3

    _render_input_editor("cf_new", _default_input_rows(), "cf_new_field_count")
    count = st.session_state.get("cf_new_field_count", 3)

    if st.button("Save draft & start validation", type="primary", key="cf_save_draft_btn"):
        try:
            inputs = _read_input_rows("cf_new", count)
            rec = create_formula(
                name,
                method,
                unit,
                category,
                package_type,
                formula_display,
                expression,
                inputs,
                use_dry_basis=use_dry,
                moisture_input_key=moisture_key or None,
                protocol_family=protocol_family,
                actor=actor,
            )
            st.session_state["cf_draft_formula_id"] = rec.id
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))


def _render_manage_tab(actor) -> None:
    formulas = list_formulas(active_only=False)
    if not formulas:
        st.info("No custom formulas yet.")
        return

    options = {f"{f.name} ({f.test_key}) — {f.status_label}": f.id for f in formulas}
    selected_label = st.selectbox(
        "Select formula",
        options=list(options.keys()),
        key="cf_manage_select",
    )
    formula_id = options[selected_label]
    rec = get_formula(formula_id)
    if rec is None:
        st.error("Formula not found.")
        return

    st.markdown(f"**Status:** {rec.status_label}")
    st.markdown(
        f"**Key:** `{rec.test_key}` · **Category:** "
        f"{all_sample_categories(include_inactive=True).get(rec.category, rec.category)}"
    )
    if rec.package_type_label:
        st.markdown(f"**Package type:** {rec.package_type_label}")
    st.markdown(f"**Version:** v{rec.current_version_no}")
    st.info(f"**Formula:** {rec.formula_display}")
    st.code(rec.expression, language=None)

    if rec.inputs:
        st.dataframe(
            [
                {
                    "Key": i.field_key,
                    "Label": i.label,
                    "Unit": i.unit or "—",
                    "Required": "Yes" if i.required else "No",
                }
                for i in rec.inputs
            ],
            use_container_width=True,
            hide_index=True,
        )

    if not rec.is_validated:
        _render_validation_wizard(rec, actor, f"cf_manage_{rec.id}")
        with st.expander("Edit draft definition", expanded=False):
            _render_edit_form(rec, actor, require_reason=False)
    elif rec.is_active:
        with st.expander("Edit formula (new version — resets validation)", expanded=False):
            _render_edit_form(rec, actor, require_reason=True)

        if st.button("Deactivate formula", key="cf_deactivate_btn"):
            try:
                deactivate_formula(formula_id, actor=actor)
                st.success("Formula deactivated.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    else:
        st.warning("This formula is deactivated and cannot be edited.")

    versions = list_versions("custom_formulas", str(formula_id), limit=10)
    if versions:
        with st.expander("Version history", expanded=False):
            for v in versions:
                st.caption(
                    f"v{v.version_no} — {v.user_name} — {v.created_at:%Y-%m-%d %H:%M} — "
                    f"{v.edit_reason}"
                )


def _render_edit_form(rec: CustomFormula, actor, *, require_reason: bool = True) -> None:
    edit_reason = ""
    if require_reason:
        edit_reason = edit_reason_field(key=f"cf_edit_reason_{rec.id}")

    name = st.text_input("Test name *", value=rec.name, key=f"cf_edit_name_{rec.id}")
    method = st.text_input("Method", value=rec.method, key=f"cf_edit_method_{rec.id}")
    unit = st.text_input("Unit", value=rec.unit, key=f"cf_edit_unit_{rec.id}")
    formula_display = st.text_input(
        "Formula display *",
        value=rec.formula_display,
        key=f"cf_edit_display_{rec.id}",
    )
    expression = st.text_input(
        "Expression *",
        value=rec.expression,
        key=f"cf_edit_expr_{rec.id}",
    )
    use_dry = st.checkbox(
        "Apply dry-basis conversion",
        value=rec.use_dry_basis,
        key=f"cf_edit_dry_{rec.id}",
    )
    moisture_key = st.text_input(
        "Moisture input field key",
        value=rec.moisture_input_key or "",
        key=f"cf_edit_moisture_key_{rec.id}",
    )
    fam_options = ["Jaggery", "Basic Nutrition"]
    fam_index = 1 if rec.protocol_family == PROTOCOL_FAMILY_NUTRITION else 0
    fam_label = st.selectbox(
        "Protocol family",
        options=fam_options,
        index=fam_index,
        key=f"cf_edit_family_{rec.id}",
    )
    protocol_family = (
        PROTOCOL_FAMILY_NUTRITION if fam_label == "Basic Nutrition" else PROTOCOL_FAMILY_JAGGERY
    )

    rows = [{"field_key": i.field_key, "label": i.label, "unit": i.unit} for i in rec.inputs]
    count_key = f"cf_edit_field_count_{rec.id}"
    if count_key not in st.session_state:
        st.session_state[count_key] = max(1, len(rows))
    count = _render_input_editor(f"cf_edit_{rec.id}", rows, count_key)

    if st.button("Save changes", key=f"cf_edit_save_{rec.id}"):
        try:
            if require_reason:
                require_edit_reason(edit_reason)
            else:
                edit_reason = edit_reason or "Draft definition update"
            inputs = _read_input_rows(f"cf_edit_{rec.id}", count)
            update_formula(
                rec.id,
                name,
                method,
                unit,
                formula_display,
                expression,
                inputs,
                edit_reason,
                use_dry_basis=use_dry,
                moisture_input_key=moisture_key or None,
                protocol_family=protocol_family,
                actor=actor,
            )
            st.success("Formula updated. Validation trials were reset if the definition changed.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
