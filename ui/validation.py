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
    If message starts with MISSING:, open the dialog; else show st.error.
    """
    if message.startswith("MISSING:"):
        fields = [f for f in message[len("MISSING:") :].split("|") if f]
        warn_missing_fields(fields)
    else:
        st.error(message)
