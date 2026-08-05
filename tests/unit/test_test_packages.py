"""Unit tests for test package service helpers."""



from __future__ import annotations



import pytest



from services.test_packages import (

    PACKAGE_TYPE_FSSAI,

    diff_package_versions,

    normalize_package_type,

    package_display_label,

    package_status_label,

    validate_package_test_sets,

    validate_test_keys,

)





def test_normalize_package_type_accepts_key_and_label():

    assert normalize_package_type("fssai") == PACKAGE_TYPE_FSSAI

    assert normalize_package_type("FSSAI") == PACKAGE_TYPE_FSSAI

    assert normalize_package_type("Nutrition Only") == "basic_nutrition"
    assert normalize_package_type("Basic Nutrition") == "basic_nutrition"

    assert normalize_package_type("invalid") is None





def test_package_display_label():

    assert package_display_label("Jaggery", PACKAGE_TYPE_FSSAI) == (

        "Jaggery — FSSAI — tests to be conducted"

    )





def test_validate_test_keys_rejects_unknown():

    with pytest.raises(ValueError, match="Unknown catalog"):

        validate_test_keys(["not_a_real_test_key"])





def test_validate_test_keys_accepts_food_catalog():

    keys = validate_test_keys(["moisture", "total_ash"])

    assert keys == ["moisture", "total_ash"]





def test_validate_package_test_sets_disjoint():

    wl, nwl = validate_package_test_sets(

        ["moisture", "total_ash"],

        ["bn_protein"],

    )

    assert wl == ["moisture", "total_ash"]

    assert nwl == ["bn_protein"]





def test_validate_package_test_sets_rejects_overlap():

    with pytest.raises(ValueError, match="both with-logo and without-logo"):

        validate_package_test_sets(["moisture"], ["moisture", "total_ash"])





def test_validate_package_test_sets_requires_at_least_one():

    with pytest.raises(ValueError, match="at least one catalog test"):

        validate_package_test_sets([], [])





def test_diff_package_versions_added_removed_unchanged():

    snap_a = {

        "version_no": 1,

        "test_keys": ["moisture", "total_ash", "sulphur_dioxide"],

    }

    snap_b = {

        "version_no": 2,

        "test_keys": ["moisture", "bn_protein"],

    }

    rows = diff_package_versions(snap_a, snap_b)

    by_key = {r.test_key: r.change for r in rows}

    assert by_key["moisture"] == "unchanged"

    assert by_key["total_ash"] == "removed"

    assert by_key["sulphur_dioxide"] == "removed"

    assert by_key["bn_protein"] == "added"





def test_diff_package_versions_preserves_order():

    snap_a = {"test_keys": ["moisture"]}

    snap_b = {"test_keys": ["moisture", "total_ash"]}

    rows = diff_package_versions(snap_a, snap_b)

    assert [r.test_key for r in rows] == ["moisture", "total_ash"]


def test_package_status_label():
    assert package_status_label({"status": "defined"}) == "Defined"
    assert package_status_label({"status": "inactive"}) == "Inactive"
    assert package_status_label({"status": "not_defined"}) == "Not defined"
    assert package_status_label({}) == "Not defined"

