"""
Unit tests for shared lab formula catalog (TC-FOR-*).
"""

from __future__ import annotations

import pytest

from services.protocols.test_catalog import (
    TEST_CATALOG,
    get_test,
    missing_required_inputs,
)


MOISTURE_CTX = {"moisture": 6.0}


class TestAppearance:
    def test_happy(self):
        display, numeric = get_test("appearance").calculate(
            {"appearance_obs": "Light brown crystalline"}, {}
        )
        assert display == "Light brown crystalline"
        assert numeric is None

    def test_missing(self):
        with pytest.raises(ValueError, match="appearance_obs"):
            get_test("appearance").calculate({"appearance_obs": "  "}, {})


class TestMoisture:
    def test_happy(self):
        display, numeric = get_test("moisture").calculate(
            {"w1": 10.5, "w2": 10.2, "w": 5.0}, {}
        )
        assert display == "6.0"
        assert numeric == 6.0

    def test_zero_weight(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("moisture").calculate({"w1": 10.5, "w2": 10.2, "w": 0}, {})

    def test_missing_required_inputs(self):
        missing = missing_required_inputs(
            get_test("moisture"),
            {"empty_dish": 1.0},
        )
        assert "Weight of dish + Sample before drying (W1)" in missing
        assert "Weight of sample taken (W)" in missing
        assert "Weight of dish + Sample after drying (W2)" in missing


class TestTotalAsh:
    def test_dry_basis_with_ctx(self):
        display, numeric = get_test("total_ash").calculate(
            {"w1": 20.0, "w2": 20.15, "w": 5.0},
            MOISTURE_CTX,
        )
        assert display == "3.19"
        assert numeric == 3.19

    def test_missing_moisture(self):
        with pytest.raises(ValueError, match="Moisture"):
            get_test("total_ash").calculate(
                {"w1": 20.0, "w2": 20.15, "w": 5.0},
                {},
            )

    def test_moisture_pct_override(self):
        display, numeric = get_test("total_ash").calculate(
            {"w1": 20.0, "w2": 20.15, "w": 5.0, "moisture_pct": 6.0},
            {},
        )
        assert numeric == 3.19
        assert display == "3.19"

    def test_moisture_100_invalid(self):
        with pytest.raises(ValueError, match="Invalid moisture"):
            get_test("total_ash").calculate(
                {"w1": 20.0, "w2": 20.15, "w": 5.0},
                {"moisture": 100.0},
            )

    def test_zero_weight(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("total_ash").calculate(
                {"w1": 20.0, "w2": 20.15, "w": 0},
                MOISTURE_CTX,
            )


class TestAcidInsoluble:
    def test_dry_basis(self):
        display, numeric = get_test("acid_insoluble_ash").calculate(
            {"w1": 20.0, "w2": 20.05, "w": 5.0},
            MOISTURE_CTX,
        )
        assert display == "1.06"
        assert numeric == 1.06

    def test_missing_moisture(self):
        with pytest.raises(ValueError, match="Moisture"):
            get_test("acid_insoluble_ash").calculate(
                {"w1": 20.0, "w2": 20.05, "w": 5.0},
                {},
            )


class TestAddedColor:
    def test_absent(self):
        display, numeric = get_test("added_color").calculate(
            {"color_result": "Absent"}, {}
        )
        assert display == "Absent"
        assert numeric is None

    def test_empty(self):
        with pytest.raises(ValueError, match="color_result"):
            get_test("added_color").calculate({"color_result": ""}, {})


class TestExtraneous:
    def test_dry_basis(self):
        display, numeric = get_test("extraneous_matter").calculate(
            {"w": 10, "w2_filter": 1.0, "w1_matter": 1.2},
            MOISTURE_CTX,
        )
        assert display == "2.13"
        assert numeric == 2.13

    def test_zero_weight(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("extraneous_matter").calculate(
                {"w": 0, "w2_filter": 1.0, "w1_matter": 1.2},
                MOISTURE_CTX,
            )


class TestInvertSugar:
    def test_dry_basis(self):
        display, numeric = get_test("invert_sugar").calculate(
            {"sugar_conc": 0.5, "sample_wt": 5.0, "br_invert": 25.0},
            MOISTURE_CTX,
        )
        assert display == "106.38"
        assert numeric == 106.38

    def test_zero_br(self):
        with pytest.raises(ValueError, match="non-zero"):
            get_test("invert_sugar").calculate(
                {"sugar_conc": 0.5, "sample_wt": 5.0, "br_invert": 0},
                MOISTURE_CTX,
            )


class TestReducingSugar:
    def test_dry_basis(self):
        display, numeric = get_test("reducing_sugar").calculate(
            {"sugar_conc": 0.5, "sample_wt": 5.0, "br_reducing": 50.0},
            MOISTURE_CTX,
        )
        assert display == "53.19"
        assert numeric == 53.19


class TestSucrose:
    def test_from_context(self):
        display, numeric = get_test("sucrose").calculate(
            {},
            {"invert_sugar": 106.38, "reducing_sugar": 53.19},
        )
        assert display == "53.19"
        assert numeric == 53.19

    def test_manual_override(self):
        display, numeric = get_test("sucrose").calculate(
            {"invert_dry": 80, "reducing_dry": 30},
            {},
        )
        assert display == "50.0"
        assert numeric == 50.0

    def test_missing_deps(self):
        with pytest.raises(ValueError, match="invert_sugar"):
            get_test("sucrose").calculate({}, {})


class TestSulphatedAsh:
    def test_dry_basis(self):
        display, numeric = get_test("sulphated_ash").calculate(
            {"w1": 20.0, "w2": 20.15, "w": 5.0},
            MOISTURE_CTX,
        )
        assert display == "3.19"
        assert numeric == 3.19


class TestSulphurDioxide:
    def test_ppm(self):
        display, numeric = get_test("sulphur_dioxide").calculate(
            {"ug_so4": 25.0, "sample_wt": 5.0},
            {},
        )
        assert display == "50.0"
        assert numeric == 50.0

    def test_zero_weight(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("sulphur_dioxide").calculate(
                {"ug_so4": 25.0, "sample_wt": 0},
                {},
            )


class TestCatalogMeta:
    def test_eleven_tests(self):
        assert len(TEST_CATALOG) == 11

    def test_all_current_tests_are_food(self):
        from services.protocols.test_catalog import CATEGORY_FOOD, tests_for_category

        food_keys = {t.key for t in tests_for_category(CATEGORY_FOOD)}
        assert food_keys == set(TEST_CATALOG.keys())

    def test_water_and_feed_empty_until_formulas_added(self):
        from services.protocols.test_catalog import (
            CATEGORY_CATTLE_FEED_FERTILIZER,
            CATEGORY_WATER,
            list_tests_for_select,
            tests_for_category,
        )

        assert tests_for_category(CATEGORY_WATER) == []
        assert tests_for_category(CATEGORY_CATTLE_FEED_FERTILIZER) == []
        assert list_tests_for_select(CATEGORY_WATER) == []

    def test_list_tests_for_select_food_filtered(self):
        from services.protocols.test_catalog import CATEGORY_FOOD, list_tests_for_select

        options = list_tests_for_select(CATEGORY_FOOD)
        assert len(options) == 11
        assert all(isinstance(k, str) and isinstance(lbl, str) for k, lbl in options)

    def test_filter_keys_for_category(self):
        from services.protocols.test_catalog import (
            CATEGORY_FOOD,
            CATEGORY_WATER,
            filter_keys_for_category,
        )

        assert filter_keys_for_category(["moisture", "total_ash"], CATEGORY_FOOD) == [
            "moisture",
            "total_ash",
        ]
        assert filter_keys_for_category(["moisture"], CATEGORY_WATER) == []

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_test("not_a_real_test")

    def test_invalid_numeric_raises(self):
        with pytest.raises((ValueError, TypeError)):
            get_test("moisture").calculate(
                {"w1": "abc", "w2": 10.2, "w": 5.0},
                {},
            )
