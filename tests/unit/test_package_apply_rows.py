"""Unit tests for append-by-Apply test package intake rows."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from ui.components import (
    INTAKE_PACKAGE_APPLY_STACK_KEY,
    _default_sample_rows,
    _normalize_ctr_df,
    build_sample_df_after_package_apply,
    clear_ctr_form_state,
    rebuild_sample_df_from_apply_stack,
)


def _pkg(name: str, *, package_type: str = "fssai") -> SimpleNamespace:
    return SimpleNamespace(
        id=101,
        sample_product_name=name,
        package_type=package_type,
        package_type_label="FSSAI",
        test_keys_with_logo=["moisture"],
        test_keys_without_logo=[],
    )


def test_apply_fills_single_empty_row_as_sr_1():
    empty = pd.DataFrame(_default_sample_rows(1))
    df, target_sr = build_sample_df_after_package_apply(empty, _pkg("Jaggery"))
    assert target_sr == 1
    assert len(df) == 1
    assert int(df.iloc[0]["Sr. No"]) == 1
    assert df.iloc[0]["Name of sample"] == "Jaggery"


def test_apply_appends_second_row():
    first = _normalize_ctr_df(
        pd.DataFrame(
            [
                {
                    "Sr. No": 1,
                    "Category": "Food",
                    "Name of sample": "Jaggery",
                    "Code/batch no.": "",
                    "Sample qty.": "500 g",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                }
            ]
        )
    )
    df, target_sr = build_sample_df_after_package_apply(first, _pkg("Honey"))
    assert target_sr == 2
    assert len(df) == 2
    assert list(df["Sr. No"].astype(int)) == [1, 2]
    assert df.iloc[0]["Name of sample"] == "Jaggery"
    assert df.iloc[1]["Name of sample"] == "Honey"


def test_apply_appends_third_row_sequential_sr():
    two = _normalize_ctr_df(
        pd.DataFrame(
            [
                {
                    "Sr. No": 1,
                    "Category": "Food",
                    "Name of sample": "A",
                    "Code/batch no.": "",
                    "Sample qty.": "1",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                },
                {
                    "Sr. No": 2,
                    "Category": "Food",
                    "Name of sample": "B",
                    "Code/batch no.": "",
                    "Sample qty.": "2",
                    "Parameters": "FSSAI",
                    "_sample_id": None,
                    "_status": "pending",
                },
            ]
        )
    )
    df, target_sr = build_sample_df_after_package_apply(two, _pkg("C"))
    assert target_sr == 3
    assert list(df["Sr. No"].astype(int)) == [1, 2, 3]
    assert df.iloc[2]["Name of sample"] == "C"


def _loader(*packages: SimpleNamespace):
    by_id = {p.id: p for p in packages}

    def load(pkg_id: int):
        return by_id.get(int(pkg_id))

    return load


def test_rebuild_stack_one_product():
    j = _pkg("Jaggery", package_type="fssai")
    j.id = 10
    df = rebuild_sample_df_from_apply_stack([10], get_package_fn=_loader(j))
    assert len(df) == 1
    assert df.iloc[0]["Name of sample"] == "Jaggery"


def test_rebuild_stack_two_products_preserves_first_row_qty():
    j = _pkg("Jaggery")
    j.id = 10
    h = _pkg("Honey")
    h.id = 20
    preserved = [
        {
            "Code/batch no.": "B-01",
            "Sample qty.": "500 g",
        }
    ]
    df = rebuild_sample_df_from_apply_stack(
        [10, 20], preserved, get_package_fn=_loader(j, h)
    )
    assert len(df) == 2
    assert df.iloc[0]["Name of sample"] == "Jaggery"
    assert df.iloc[0]["Sample qty."] == "500 g"
    assert df.iloc[0]["Code/batch no."] == "B-01"
    assert df.iloc[1]["Name of sample"] == "Honey"


def test_rebuild_stack_same_product_twice_preserves_batches():
    d = _pkg("Dhane Powder")
    d.id = 10
    preserved = [
        {"Code/batch no.": "02", "Sample qty.": "100 gm"},
        {"Code/batch no.": "05", "Sample qty.": "200 gm"},
    ]
    df = rebuild_sample_df_from_apply_stack(
        [10, 10], preserved, get_package_fn=_loader(d)
    )
    assert len(df) == 2
    assert list(df["Name of sample"]) == ["Dhane Powder", "Dhane Powder"]
    assert df.iloc[0]["Code/batch no."] == "02"
    assert df.iloc[1]["Code/batch no."] == "05"
    assert list(df["Sr. No"].astype(int)) == [1, 2]


def test_rebuild_stack_appends_manual_suffix_row():
    j = _pkg("Jaggery")
    j.id = 10
    preserved = [
        {"Code/batch no.": "", "Sample qty.": "1 kg"},
        {
            "Sr. No": 2,
            "Category": "Water",
            "Name of sample": "Potable Water",
            "Code/batch no.": "W-1",
            "Sample qty.": "500 ml",
            "Parameters": "",
            "_sample_id": None,
            "_status": "pending",
        },
    ]
    df = rebuild_sample_df_from_apply_stack([10], preserved, get_package_fn=_loader(j))
    assert len(df) == 2
    assert df.iloc[0]["Name of sample"] == "Jaggery"
    assert df.iloc[1]["Category"] == "Water"
    assert df.iloc[1]["Name of sample"] == "Potable Water"
    assert list(df["Sr. No"].astype(int)) == [1, 2]


def test_clear_ctr_form_state_removes_apply_stack():
    import streamlit as st

    st.session_state[INTAKE_PACKAGE_APPLY_STACK_KEY] = [1, 2]
    clear_ctr_form_state()
    assert INTAKE_PACKAGE_APPLY_STACK_KEY not in st.session_state

