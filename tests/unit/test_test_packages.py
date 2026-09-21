"""Unit tests for test package service helpers."""



from __future__ import annotations



from unittest.mock import MagicMock, patch



import pytest



from services.test_packages import (

    PACKAGE_TYPE_FSSAI,

    TestPackage,

    _similarity_score,

    create_package_from_source,

    diff_package_versions,

    find_similar_packages,

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


def test_similarity_haldi_powder_vs_haldi():
    score = _similarity_score("Haldi Powder", "Haldi")
    assert score is not None
    assert score[0] >= 2
    assert score[1] in ("prefix", "contains")


def test_similarity_goda_masala_vs_masala():
    score = _similarity_score("Goda Masala", "Masala")
    assert score is not None
    assert score[1] in ("contains", "word")


def test_similarity_kanda_lasun_masala_vs_masala():
    score = _similarity_score("Kanda Lasun Masala", "Masala")
    assert score is not None
    assert score[1] in ("contains", "word")


def test_similarity_exact_match_returns_none():
    assert _similarity_score("Haldi Powder", "Haldi Powder") is None


def test_similarity_unrelated_names_returns_none():
    assert _similarity_score("Potable Water", "Jaggery") is None


def _mock_package(
    pkg_id: int,
    name: str,
    *,
    wl: list[str] | None = None,
    nwl: list[str] | None = None,
) -> TestPackage:
    wl = wl or ["moisture", "total_ash"]
    nwl = nwl or []
    return TestPackage(
        id=pkg_id,
        sample_product_name=name,
        package_type=PACKAGE_TYPE_FSSAI,
        category="food",
        current_version_no=1,
        is_active=True,
        test_keys_with_logo=wl,
        test_keys_without_logo=nwl,
    )


@patch("services.test_packages.list_packages")
def test_find_similar_packages_ranks_prefix_match(mock_list_packages):
    mock_list_packages.return_value = [
        _mock_package(1, "Haldi"),
        _mock_package(2, "Unrelated Spice"),
    ]
    matches = find_similar_packages("Haldi Powder")
    assert len(matches) == 1
    assert matches[0]["sample_product_name"] == "Haldi"
    assert matches[0]["match_reason"] in ("prefix", "contains")
    assert matches[0]["test_count"] == 2


@patch("services.test_packages.list_packages")
def test_find_similar_packages_excludes_exact_name(mock_list_packages):
    mock_list_packages.return_value = [
        _mock_package(1, "Haldi Powder"),
        _mock_package(2, "Haldi"),
    ]
    matches = find_similar_packages("Haldi Powder")
    assert [m["sample_product_name"] for m in matches] == ["Haldi"]


@patch("services.test_packages.list_packages")
def test_find_similar_packages_empty_when_unrelated(mock_list_packages):
    mock_list_packages.return_value = [
        _mock_package(1, "Jaggery"),
        _mock_package(2, "Potable Water"),
    ]
    assert find_similar_packages("Random Sauce") == []


@patch("services.test_packages.log_from_user")
@patch("services.test_packages.create_package")
@patch("services.test_packages.resolve_package_for_product")
@patch("services.test_packages.get_package")
def test_create_package_from_source_copies_tests(
    mock_get_package,
    mock_resolve,
    mock_create_package,
    mock_log,
):
    source = _mock_package(5, "Haldi", wl=["moisture"], nwl=["bn_protein"])
    mock_get_package.return_value = source
    mock_resolve.return_value = None
    created = _mock_package(10, "Haldi Powder", wl=["moisture"], nwl=["bn_protein"])
    mock_create_package.return_value = created

    result = create_package_from_source("Haldi Powder", 5)

    mock_create_package.assert_called_once_with(
        "Haldi Powder",
        PACKAGE_TYPE_FSSAI,
        ["moisture"],
        ["bn_protein"],
        category="food",
        actor=None,
    )
    assert result.id == 10
    mock_log.assert_called_once()
    assert mock_log.call_args[0][1] == "package.create_from_similar"


@patch("services.test_packages.resolve_package_for_product")
@patch("services.test_packages.get_package")
def test_create_package_from_source_rejects_duplicate_name(
    mock_get_package,
    mock_resolve,
):
    mock_get_package.return_value = _mock_package(5, "Haldi")
    mock_resolve.return_value = MagicMock()

    with pytest.raises(ValueError, match="already exists"):
        create_package_from_source("Haldi Powder", 5)


def test_validate_test_keys_accepts_full_food_catalog_mix():
    from services.protocols.test_catalog import FOOD_TEST_KEYS

    keys = validate_test_keys(["moisture", "bn_protein", "bn_moisture"])
    assert keys == ["moisture", "bn_protein", "bn_moisture"]
    assert all(k in FOOD_TEST_KEYS for k in keys)


def test_list_tests_for_select_labels_hide_internal_keys():
    from services.protocols.test_catalog import CATEGORY_FOOD, list_tests_for_select

    for _key, label in list_tests_for_select(CATEGORY_FOOD):
        assert "bn_" not in label

