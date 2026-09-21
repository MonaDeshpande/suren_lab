"""
ui/reviewer_state.py
--------------------
Per-sample Reviewer report form state for pages/3_Reviewer.py.

Streamlit widgets require flat session_state keys; this module centralizes
the active sample pointer, initialization tracking, specs DataFrame storage,
and stale-key cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

_ACTIVE_SAMPLE_KEY = "active_sample_code"
_STATES_KEY = "reviewer_report_states"

_WIDGET_FIELDS = (
    "condition",
    "appearance",
    "testing_at",
    "ulr",
    "report_chem",
    "report_micro",
    "report_no",
    "customer_sid",
    "customer_addr",
    "report_date",
    "batch_no",
    "lab_code",
    "tests_processed",
    "location",
    "sampling_method",
    "auth_signatory",
    "checked_by",
    "remark",
    "disclaimer",
)

_PRESERVED_KEYS = frozenset(
    {
        "reviewer_search_by",
        "reviewer_search_query",
        "reviewer_search_hits",
        "reviewer_pick_code",
        "reviewer_queue_pick",
        "reviewer_note",
        "reviewer_pdf_for",
        "reviewer_pdf_bytes",
        "reviewer_pdf_name",
        "reviewer_report_for",
        "reviewer_report_is_water",
        "reviewer_report_is_micro",
        "reviewer_docx_bytes",
        "reviewer_docx_name",
        _ACTIVE_SAMPLE_KEY,
        _STATES_KEY,
        "reviewer_report_fields_for",
        "gen_final_report",
        "dl_final_report_docx",
        "dl_final_report_pdf",
    }
)


@dataclass
class ReviewerReportState:
    """In-memory report draft for one sample (non-widget data + init flag)."""

    sample_code: str
    initialized: bool = False
    specs_df: pd.DataFrame = field(default_factory=pd.DataFrame)


def widget_key(field: str, sample_code: str) -> str:
    """Stable Streamlit widget key (matches legacy naming)."""
    return f"reviewer_{field}_{sample_code}"


def spec_editor_key(sample_code: str, *, is_water: bool) -> str:
    suffix = "water_spec_editor" if is_water else "spec_editor"
    return f"reviewer_{suffix}_{sample_code}"


def _states_bucket() -> dict[str, ReviewerReportState]:
    if _STATES_KEY not in st.session_state:
        st.session_state[_STATES_KEY] = {}
    bucket = st.session_state[_STATES_KEY]
    if not isinstance(bucket, dict):
        bucket = {}
        st.session_state[_STATES_KEY] = bucket
    return bucket


def get_reviewer_state(sample_code: str) -> ReviewerReportState:
    """Return (and create) the dataclass for sample_code."""
    code = (sample_code or "").strip()
    bucket = _states_bucket()
    state = bucket.get(code)
    if state is None or state.sample_code != code:
        state = ReviewerReportState(sample_code=code)
        bucket[code] = state
    return state


def is_initialized(sample_code: str) -> bool:
    return get_reviewer_state(sample_code).initialized


def mark_initialized(sample_code: str) -> None:
    get_reviewer_state(sample_code).initialized = True


def get_specs_df(sample_code: str) -> pd.DataFrame:
    return get_reviewer_state(sample_code).specs_df


def set_specs_df(sample_code: str, df: pd.DataFrame) -> None:
    get_reviewer_state(sample_code).specs_df = df


def set_widget_default(field: str, sample_code: str, value: Any) -> None:
    """Set a widget value only when the key is not yet present."""
    key = widget_key(field, sample_code)
    if key not in st.session_state:
        st.session_state[key] = value


def get_widget(field: str, sample_code: str, default: Any = "") -> Any:
    return st.session_state.get(widget_key(field, sample_code), default)


def set_widget(field: str, sample_code: str, value: Any) -> None:
    st.session_state[widget_key(field, sample_code)] = value


def _sample_code_from_widget_key(key: str) -> str | None:
    """Extract sample code suffix from a per-sample reviewer widget key."""
    for field in _WIDGET_FIELDS:
        prefix = f"reviewer_{field}_"
        if key.startswith(prefix):
            return key[len(prefix) :]
    for marker in ("reviewer_water_spec_editor_", "reviewer_spec_editor_"):
        if key.startswith(marker):
            return key[len(marker) :]
    legacy = "reviewer_specs_"
    if key.startswith(legacy):
        return key[len(legacy) :]
    return None


def purge_stale_reviewer_state(active_sample_code: str) -> None:
    """
    Drop cached draft state for samples other than the active one.

    Does not touch PDF/download cache keys (reviewer_pdf_*, reviewer_docx_*).
    """
    active = (active_sample_code or "").strip()
    keep = {active}

    bucket = _states_bucket()
    for code in list(bucket.keys()):
        if code not in keep:
            del bucket[code]

    for key in list(st.session_state.keys()):
        if not isinstance(key, str) or key in _PRESERVED_KEYS:
            continue
        if not key.startswith("reviewer_"):
            continue
        code = _sample_code_from_widget_key(key)
        if code is not None and code not in keep:
            st.session_state.pop(key, None)

    st.session_state.pop("reviewer_report_fields_for", None)


def on_sample_selected(sample_code: str) -> ReviewerReportState:
    """Update active_sample_code, purge stale drafts, return current state."""
    code = (sample_code or "").strip()
    prev = st.session_state.get(_ACTIVE_SAMPLE_KEY)
    st.session_state[_ACTIVE_SAMPLE_KEY] = code
    if prev and prev != code:
        purge_stale_reviewer_state(code)
    return get_reviewer_state(code)
