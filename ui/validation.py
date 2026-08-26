"""
ui/validation.py
----------------
Popup helpers when the analyst leaves required worksheet fields empty.
"""

from __future__ import annotations

import streamlit as st


@st.dialog("Missing fields")
def warn_missing_fields(fields: list[str]) -> None:
    """
    Modal popup listing required inputs the analyst left blank.

    Close with the button; then fill the fields and save again.
    """
    st.markdown("Please complete these required fields before saving:")
    for label in fields:
        st.write(f"• **{label}**")
    if st.button("OK", type="primary", use_container_width=True):
        st.rerun()


def show_missing_or_error(message: str) -> None:
    """
    If message starts with MISSING:, DECIMALS:, or MOISTURE_REQUIRED:, open the dialog; else show st.error.
    """
    if message.startswith("MISSING:"):
        fields = [f for f in message[len("MISSING:") :].split("|") if f]
        warn_missing_fields(fields)
    elif message.startswith("DECIMALS:"):
        fields = [f for f in message[len("DECIMALS:") :].split("|") if f]
        warn_decimal_places(fields)
    elif message.startswith("MOISTURE_REQUIRED:"):
        warn_moisture_required(message[len("MOISTURE_REQUIRED:") :].strip())
    else:
        st.error(message)


@st.dialog("Too many decimal places")
def warn_decimal_places(fields: list[str]) -> None:
    """Modal when a numeric input exceeds four decimal places."""
    st.markdown("These fields allow at most **4 decimal places**:")
    for label in fields:
        st.write(f"• **{label}**")
    if st.button("OK", type="primary", use_container_width=True):
        st.rerun()


@st.dialog("Moisture required")
def warn_moisture_required(detail: str) -> None:
    """Modal when a dry-basis test is saved before Moisture."""
    st.markdown(
        "**Save the Moisture test first.**\n\n"
        "This calculation uses the saved Moisture % for dry-basis conversion. "
        "Complete and save **Moisture** on this sample, then return to this test."
    )
    if detail:
        st.caption(detail)
    if st.button("OK", type="primary", use_container_width=True):
        st.rerun()
