"""
services/ctr_symbols.py
-----------------------
Shared CTR checkbox / mark symbols for PDF and DOCX output.
"""

from __future__ import annotations

from typing import Optional

CHECK_MARK = "\u2713"
EMPTY_MARK = " "

# Unicode sub/superscript digits → ASCII for CTR/PDF fonts that lack those glyphs
_SCRIPT_TO_ASCII = str.maketrans(
    {
        "\u2080": "0",
        "\u2081": "1",
        "\u2082": "2",
        "\u2083": "3",
        "\u2084": "4",
        "\u2085": "5",
        "\u2086": "6",
        "\u2087": "7",
        "\u2088": "8",
        "\u2089": "9",
        "\u00b3": "3",
        "\u00b2": "2",
        "\u00b9": "1",
    }
)


def normalize_ctr_display_text(text: str) -> str:
    """Make catalog names safe for CTR PDF/DOCX (e.g. CaCO₃ → CaCO3)."""
    return (text or "").translate(_SCRIPT_TO_ASCII)


def selected_mark(selected: bool) -> str:
    """Return checkmark or blank for bracket-style CTR marks."""
    return CHECK_MARK if selected else EMPTY_MARK


def bracket_mark(selected: bool) -> str:
    """Return ``[✓]`` or ``[ ]`` for inline option lists."""
    return f"[{selected_mark(selected)}]"


def yes_no_option_line(value: Optional[bool]) -> str:
    """CTR Yes/No row: single brackets around checkmark or space."""
    if value is True:
        return (
            f"Yes  [{selected_mark(True)}]                                   "
            f"No  [{selected_mark(False)}]"
        )
    if value is False:
        return (
            f"Yes  [{selected_mark(False)}]                                   "
            f"No  [{selected_mark(True)}]"
        )
    return (
        f"Yes  [{selected_mark(False)}]                                   "
        f"No  [{selected_mark(False)}]"
    )


def yes_no_remark(value: bool | None) -> str:
    """Checklist Yes/No remark using checkmarks instead of X."""
    if value is True:
        return f"Yes ( {CHECK_MARK} ) No (  )"
    if value is False:
        return f"Yes (  ) No ( {CHECK_MARK} )"
    return "Yes (  ) No (  )"
