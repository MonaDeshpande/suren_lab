"""Admin panel: food report signatories and disclaimer defaults."""

from __future__ import annotations

import streamlit as st

from services.audit import log_from_user
from services.report_settings import (
    ReportSettings,
    load_report_settings,
    save_report_settings,
)
from services.test_report_pdf import DISCLAIMER_BULLETS, REMARK_TEXT
from ui.components import render_section_title


def render_report_settings_panel(actor) -> None:
    render_section_title(
        "Report settings — food final report",
        "Default signatory names and disclaimer text for food chemical test reports.",
    )
    settings = load_report_settings()

    with st.form("report_settings_form"):
        st.markdown("**Signatories** (Reviewer picks from this list)")
        names_text = st.text_area(
            "Names (one per line: `Name | Role`)",
            value="\n".join(
                f"{s['name']} | {s.get('role', '')}" for s in settings.signatories
            ),
            height=120,
            help="Example: Dr. Surendra Nashikkar | Director",
        )
        disclaimer_text = st.text_area(
            "Disclaimer bullets (one per line)",
            value="\n".join(settings.disclaimer_bullets or DISCLAIMER_BULLETS),
            height=180,
        )
        remark_text = st.text_area(
            "Default remark paragraph",
            value=settings.default_remark_text or REMARK_TEXT,
            height=120,
        )
        submitted = st.form_submit_button("Save report settings", type="primary")

    if submitted:
        signatories: list[dict[str, str]] = []
        for line in names_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                name, role = [p.strip() for p in line.split("|", 1)]
            else:
                name, role = line, ""
            if name:
                signatories.append({"name": name, "role": role})
        bullets = [ln.strip() for ln in disclaimer_text.splitlines() if ln.strip()]
        new_settings = ReportSettings(
            signatories=signatories or settings.signatories,
            disclaimer_bullets=bullets or list(DISCLAIMER_BULLETS),
            default_remark_text=(remark_text or "").strip() or REMARK_TEXT,
        )
        save_report_settings(new_settings)
        log_from_user(actor, "report_settings.update", "report_settings", "food", {})
        st.success("Report settings saved.")
