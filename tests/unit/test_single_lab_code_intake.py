"""Unit tests for one Lab Code per multi-sample CTR request."""

from __future__ import annotations

import pandas as pd

from services.requests import request_lab_code_for_verification
from services.samples import derive_sample_code
from ui.components import _normalize_ctr_df, _sample_code_preview_map


def test_request_lab_code_for_verification_normalizes():
    assert request_lab_code_for_verification("  sls/26/306  ") == "SLS/26/306"


def test_sample_code_preview_two_rows_same_base():
    df = _normalize_ctr_df(
        pd.DataFrame(
            [
                {
                    "Sr. No": 1,
                    "Category": "Food",
                    "Name of sample": "A",
                    "Code/batch no.": "",
                    "Sample qty.": "",
                    "Parameters": "",
                    "_sample_id": None,
                    "_status": "pending",
                },
                {
                    "Sr. No": 2,
                    "Category": "Water",
                    "Name of sample": "Potable Water",
                    "Code/batch no.": "",
                    "Sample qty.": "1 L",
                    "Parameters": "",
                    "_sample_id": None,
                    "_status": "pending",
                },
            ]
        )
    )
    lab = "SLS/26/900"
    codes = _sample_code_preview_map(lab, df)
    assert codes[1] == derive_sample_code(lab, index=1, total=2)
    assert codes[2] == derive_sample_code(lab, index=2, total=2)
    assert request_lab_code_for_verification(lab) == "SLS/26/900"
    assert codes[1].startswith("SLS/26/900/")
    assert codes[2].startswith("SLS/26/900/")
