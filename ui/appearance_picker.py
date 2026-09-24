"""
ui/appearance_picker.py
-----------------------
Searchable appearance master picker for Analyst forms.
"""

from __future__ import annotations

import streamlit as st

from services.appearance_master import get_or_create_appearance, search_appearances

APPEARANCE_OTHER = "Other (custom)"


def _default_choice(stored_value: str, option_texts: list[str]) -> str:
    stored = (stored_value or "").strip()
    if not stored:
        return ""
    if stored in option_texts:
        return stored
    return APPEARANCE_OTHER


def render_appearance_picker(
    key_prefix: str,
    stored_value: str,
    *,
    search_label: str = "Search appearance",
    select_label: str = "Appearance",
) -> tuple[str, str]:
    """
    Render search + select + optional custom field (safe inside ``st.form``).

    Returns ``(selectbox_choice, custom_text)`` where choice may be
    ``APPEARANCE_OTHER`` or a master string.
    """
    prefix = (key_prefix or "app").strip()
    search_q = st.text_input(
        search_label,
        value="",
        key=f"{prefix}_appearance_search",
        help="Type to filter the master list. Leave empty to show recent entries.",
    )
    matches = search_appearances(search_q, limit=40)
    option_texts = [o.appearance_text for o in matches]
    stored = (stored_value or "").strip()
    if stored and stored not in option_texts:
        option_texts = [stored] + option_texts

    select_options = [""] + option_texts + [APPEARANCE_OTHER]
    default_choice = _default_choice(stored, option_texts)
    index = (
        select_options.index(default_choice)
        if default_choice in select_options
        else 0
    )
    choice = st.selectbox(
        select_label,
        options=select_options,
        index=index,
        key=f"{prefix}_appearance_select",
        help="Pick from master list or enter a custom value.",
    )
    custom = ""
    if choice == APPEARANCE_OTHER:
        custom_default = stored if default_choice == APPEARANCE_OTHER else ""
        custom = st.text_input(
            "Custom appearance",
            value=custom_default,
            key=f"{prefix}_appearance_custom",
        )
    return choice, custom


def resolve_appearance_text(choice: str, custom: str) -> str:
    """Map picker output to canonical appearance text (creates master row if custom)."""
    if choice == APPEARANCE_OTHER:
        return get_or_create_appearance(custom).appearance_text
    cleaned = (choice or "").strip()
    if not cleaned:
        raise ValueError("Appearance text is required.")
    return cleaned
