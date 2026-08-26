"""
services/ulr.py
---------------
Generate ULR numbers for final test reports.

Format: TC16118 + YY + zero-padded lab digits (9) + F
Example: SLS/26/306/01 → TC1611826000030601F
"""

from __future__ import annotations

import re
from datetime import date

ULR_PREFIX = "TC16118"
ULR_SUFFIX = "F"
ULR_MIDDLE_WIDTH = 9
ULR_TOTAL_LENGTH = len(ULR_PREFIX) + 2 + ULR_MIDDLE_WIDTH + len(ULR_SUFFIX)


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def parse_ulr_parts(lab_code: str, *, fallback_year: int | None = None) -> tuple[str, str] | None:
    """
    Parse lab code into (year_2digit, lab_digit_body).

    Expects at least 4 slash-separated segments: prefix/year/main/sample/...
    Lab digit body = main + sample (segments at index 2 and 3).
    """
    parts = [p.strip() for p in (lab_code or "").split("/") if p.strip()]
    if len(parts) < 4:
        return None

    year_raw = parts[1]
    year_digits = _digits_only(year_raw)
    if len(year_digits) >= 2:
        year = year_digits[-2:]
    elif fallback_year is not None:
        year = f"{fallback_year % 100:02d}"
    else:
        year = f"{date.today().year % 100:02d}"

    main = _digits_only(parts[2])
    sample = _digits_only(parts[3])
    if not main and not sample:
        return None

    return year, f"{main}{sample}"


def generate_ulr_no(lab_code: str, *, fallback_year: int | None = None) -> str:
    """
    Build a ULR from a lab code string.

    Returns empty string when the code cannot be parsed.
    """
    parsed = parse_ulr_parts(lab_code, fallback_year=fallback_year)
    if parsed is None:
        return ""
    year, body = parsed
    middle = body.zfill(ULR_MIDDLE_WIDTH)
    ulr = f"{ULR_PREFIX}{year}{middle}{ULR_SUFFIX}"
    if len(ulr) != ULR_TOTAL_LENGTH:
        return ""
    return ulr


def lab_code_for_ulr(lab_code: str | None, sample_code: str | None) -> str:
    """Prefer lab_code when it has enough segments; else sample_code."""
    lab = (lab_code or "").strip()
    code = (sample_code or "").strip()
    if len([p for p in lab.split("/") if p.strip()]) >= 4:
        return lab
    if len([p for p in code.split("/") if p.strip()]) >= 4:
        return code
    return lab or code
