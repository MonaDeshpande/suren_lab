"""
services/number_format.py
-------------------------
Shared numeric formatting for analyst inputs, saved results, and test reports.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


def decimal_places(text: str) -> int:
    """Count digits after the decimal point in a numeric string."""
    raw = (text or "").strip()
    if not raw:
        return 0
    if "." not in raw and "e" not in raw.lower():
        return 0
    try:
        dec = Decimal(raw)
    except InvalidOperation:
        return 0
    exp = dec.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def validate_max_decimals(text: str, max_places: int = 4) -> None:
    """Raise ValueError when a numeric string exceeds max decimal places."""
    raw = (text or "").strip()
    if not raw:
        return
    try:
        float(raw)
    except (TypeError, ValueError):
        return
    if decimal_places(raw) > max_places:
        raise ValueError(
            f"Maximum {max_places} decimal places allowed (got {decimal_places(raw)})."
        )


def format_input_number(value: object, *, max_places: int = 4) -> str:
    """Format worksheet / stored input values (up to 4 decimals, trim zeros)."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    text = f"{n:.{max_places}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def format_final_number(value: object) -> str:
    """Format saved catalog results to exactly 2 decimal places."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    return f"{n:.2f}"


def format_report_number(value: object) -> str:
    """
    Format numeric Test Report results.

    Values in [0, 10) are zero-padded to two digits before the decimal (01.19).
    Values >= 10 use two decimals without leading zero (12.34).
    Non-numeric text (Absent, Agreeable) is returned unchanged.
    """
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return raw
    if 0 <= n < 10:
        return f"{n:05.2f}"
    return f"{n:.2f}"


def strip_analyst_label_suffix(label: str) -> str:
    """Remove trailing ' (username)' from legacy analyst picker labels."""
    text = (label or "").strip()
    if not text:
        return ""
    match = re.match(r"^(.*)\s+\([^()]+\)\s*$", text)
    if match:
        return match.group(1).strip()
    return text
