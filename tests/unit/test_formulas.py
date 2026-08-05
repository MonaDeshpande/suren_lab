"""
Unit tests for shared lab formula catalog (TC-FOR-*).
"""

from __future__ import annotations

import pytest

from services.protocols.test_catalog import (
    CATEGORY_FOOD,
    CATEGORY_WATER,
    FOOD_TEST_KEYS,
    JAGGERY_TEST_KEYS,
    NUTRITION_TEST_KEYS,
    TEST_CATALOG,
    WATER_TEST_KEYS,
    default_test_keys_for_category,
    get_test,
    has_mixed_food_families,
    missing_required_inputs,
    tests_for_category as _catalog_tests_for_category,
)


MOISTURE_CTX = {"moisture": 6.0}
BN_MOISTURE_CTX = {"bn_moisture": 6.0}


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
        # Conc×250×10/(Wt×B.R.) then dry: wet=5.0; dry=5×100/94≈5.32
        display, numeric = get_test("reducing_sugar").calculate(
            {"sugar_conc": 0.5, "sample_wt": 5.0, "br_reducing": 50.0},
            MOISTURE_CTX,
        )
        assert display == "5.32"
        assert numeric == 5.32

    def test_zero_br(self):
        with pytest.raises(ValueError, match="non-zero"):
            get_test("reducing_sugar").calculate(
                {"sugar_conc": 0.5, "sample_wt": 5.0, "br_reducing": 0},
                MOISTURE_CTX,
            )


class TestSucrose:
    def test_from_context(self):
        # (106.38 − 53.19) × 0.95 ≈ 50.53
        display, numeric = get_test("sucrose").calculate(
            {},
            {"invert_sugar": 106.38, "reducing_sugar": 53.19},
        )
        assert display == "50.53"
        assert numeric == 50.53

    def test_manual_override(self):
        # (80 − 30) × 0.95 = 47.5
        display, numeric = get_test("sucrose").calculate(
            {"invert_dry": 80, "reducing_dry": 30},
            {},
        )
        assert display == "47.5"
        assert numeric == 47.5

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


class TestWaterTds:
    def test_happy(self):
        # (12.5 - 10.0) * 1000 * 1000 / 100 = 25000
        display, numeric = get_test("tds").calculate(
            {"w": 100.0, "w1": 10.0, "w2": 12.5}, {}
        )
        assert display == "25000.0"
        assert numeric == 25000.0


class TestWaterChlorides:
    def test_happy(self):
        # (10 - 0) * 0.01 * 35.45 * 1000 / 50 = 70.9
        display, numeric = get_test("chlorides").calculate(
            {"v3": 50.0, "v1": 10.0, "v2": 0.0, "n": 0.01}, {}
        )
        assert numeric == 70.9


class TestWaterAlkalinity:
    def test_happy(self):
        # 5 * 0.02 * 50000 / 100 = 50
        display, numeric = get_test("total_alkalinity").calculate(
            {"v": 100.0, "a": 5.0, "n": 0.02}, {}
        )
        assert numeric == 50.0


class TestWaterHardness:
    def test_happy(self):
        # 10 * 1.0 * 1000 / 50 = 200
        display, numeric = get_test("total_hardness").calculate(
            {"volume": 50.0, "a": 10.0, "b": 1.0}, {}
        )
        assert numeric == 200.0


class TestWaterMagnesium:
    def test_from_context(self):
        # (200 - 80) * 0.243 = 29.16
        display, numeric = get_test("magnesium").calculate(
            {},
            {"total_hardness": 200.0, "calcium_caco3": 80.0},
        )
        assert numeric == 29.2

    def test_missing_deps(self):
        with pytest.raises(ValueError, match="total_hardness"):
            get_test("magnesium").calculate({}, {})


class TestWaterDirect:
    def test_ph(self):
        display, numeric = get_test("ph").calculate({"ph_value": 7.25}, {})
        assert display == "7.25"
        assert numeric == 7.25

    def test_odor(self):
        display, numeric = get_test("odor").calculate({"odor_obs": "None"}, {})
        assert display == "None"
        assert numeric is None


class TestWaterConductivity:
    def test_happy(self):
        display, numeric = get_test("conductivity").calculate(
            {"conductivity": 450.0}, {}
        )
        assert display == "450.0"
        assert numeric == 450.0


class TestWaterTurbidity:
    def test_happy(self):
        display, numeric = get_test("turbidity").calculate({"turbidity": 1.2}, {})
        assert display == "1.2"
        assert numeric == 1.2


class TestWaterCalciumCa:
    def test_happy(self):
        # 10 × 1.0 × 1000 / 50 = 200
        display, numeric = get_test("calcium_ca").calculate(
            {"volume": 50.0, "a": 10.0, "b": 1.0}, {}
        )
        assert display == "200.0"
        assert numeric == 200.0

    def test_zero_volume(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("calcium_ca").calculate(
                {"volume": 0.0, "a": 10.0, "b": 1.0}, {}
            )


class TestWaterCalciumCaco3:
    def test_happy(self):
        # 10 × 2.0 × 1000 / 50 = 400
        display, numeric = get_test("calcium_caco3").calculate(
            {"volume": 50.0, "a": 10.0, "c": 2.0}, {}
        )
        assert display == "400.0"
        assert numeric == 400.0


class TestBasicNutritionMoisture:
    def test_happy(self):
        display, numeric = get_test("bn_moisture").calculate(
            {"w1": 10.5, "w2": 10.2, "w": 5.0}, {}
        )
        assert display == "6.0"
        assert numeric == 6.0


class TestBasicNutritionProtein:
    def test_happy(self):
        # Nitrogen = 0.014 × 1.0 × (10 - 5) × 100 / 5 = 1.4 ; Protein = 1.4 × 6.25 = 8.75
        display, numeric = get_test("bn_protein").calculate(
            {
                "w": 5.0,
                "n_naoh": 1.0,
                "br_blank": 10.0,
                "br_sample": 5.0,
                "n_factor": 6.25,
            },
            {},
        )
        assert display == "8.75"
        assert numeric == 8.75


class TestBasicNutritionCarbohydrate:
    def test_from_context(self):
        display, numeric = get_test("bn_carbohydrate").calculate(
            {},
            {
                "bn_moisture": 6.0,
                "bn_protein": 10.0,
                "bn_total_fat": 5.0,
                "bn_total_ash": 2.0,
            },
        )
        assert numeric == 77.0


class TestBasicNutritionCalories:
    def test_from_context(self):
        display, numeric = get_test("bn_calories").calculate(
            {},
            {"bn_protein": 10.0, "bn_carbohydrate": 74.0, "bn_total_fat": 5.0},
        )
        assert numeric == 381.0


class TestBasicNutritionFat:
    def test_happy(self):
        display, numeric = get_test("bn_total_fat").calculate(
            {"w": 10.0, "w1": 20.0, "w2": 21.5}, {}
        )
        assert numeric == 15.0


class TestBasicNutritionTotalAsh:
    def test_happy(self):
        # (20.15 - 20.0) × 100 / 5 = 3.0
        display, numeric = get_test("bn_total_ash").calculate(
            {"w1": 20.0, "w2": 20.15, "w": 5.0}, {}
        )
        assert display == "3.0"
        assert numeric == 3.0

    def test_zero_weight(self):
        with pytest.raises(ValueError, match="cannot be zero"):
            get_test("bn_total_ash").calculate(
                {"w1": 20.0, "w2": 20.15, "w": 0.0}, {}
            )


class TestBasicNutritionAshInsoluble:
    def test_dry_basis(self):
        display, numeric = get_test("bn_ash_insoluble_hcl").calculate(
            {"w1": 20.0, "w2": 20.05, "w": 5.0},
            BN_MOISTURE_CTX,
        )
        assert display == "1.06"
        assert numeric == 1.06

    def test_missing_moisture(self):
        with pytest.raises(ValueError, match="Moisture"):
            get_test("bn_ash_insoluble_hcl").calculate(
                {"w1": 20.0, "w2": 20.05, "w": 5.0},
                {},
            )


class TestBasicNutritionCrudeFibre:
    def test_happy(self):
        display, numeric = get_test("bn_crude_fibre").calculate(
            {"w": 10.0, "w1": 20.0, "w2": 21.5}, {}
        )
        assert display == "15.0"
        assert numeric == 15.0


class TestBasicNutritionAddedSugar:
    def test_dry_basis(self):
        # wet = 0.5×250×10/(5×50)=5.0; dry=5×100/94≈5.32
        display, numeric = get_test("bn_added_sugar").calculate(
            {"sugar_conc": 0.5, "sample_wt": 5.0, "br": 50.0},
            BN_MOISTURE_CTX,
        )
        assert display == "5.32"
        assert numeric == 5.32

    def test_zero_br(self):
        with pytest.raises(ValueError, match="non-zero"):
            get_test("bn_added_sugar").calculate(
                {"sugar_conc": 0.5, "sample_wt": 5.0, "br": 0},
                BN_MOISTURE_CTX,
            )


class TestBasicNutritionTotalSugar:
    def test_dry_basis(self):
        # wet = 0.5×250×100/(5×25)=100; dry=100×100/94≈106.38
        display, numeric = get_test("bn_total_sugar").calculate(
            {"sugar_conc": 0.5, "sample_wt": 5.0, "br": 25.0},
            BN_MOISTURE_CTX,
        )
        assert display == "106.38"
        assert numeric == 106.38


class TestCatalogMeta:
    def test_thirty_two_tests(self):
        assert len(TEST_CATALOG) == 32

    def test_food_tests_count(self):
        food_keys = {t.key for t in _catalog_tests_for_category(CATEGORY_FOOD)}
        assert len(food_keys) == 21
        assert len(FOOD_TEST_KEYS) == 21
        assert food_keys == {k for k, t in TEST_CATALOG.items() if CATEGORY_FOOD in t.categories}

    def test_food_protocol_row_breakdown(self):
        """11 Jaggery + 11 Basic Nutrition protocol rows share one Appearance key."""
        assert len(JAGGERY_TEST_KEYS) == 11
        assert len(NUTRITION_TEST_KEYS) == 11
        assert len(FOOD_TEST_KEYS) == 21
        assert JAGGERY_TEST_KEYS[0] == NUTRITION_TEST_KEYS[0] == "appearance"

    def test_nutrition_keys(self):
        assert len(NUTRITION_TEST_KEYS) == 11
        assert all(k in FOOD_TEST_KEYS for k in NUTRITION_TEST_KEYS)

    def test_mixed_families_detection(self):
        assert has_mixed_food_families(["moisture", "bn_protein"])
        assert not has_mixed_food_families(["moisture", "total_ash"])
        assert not has_mixed_food_families(["bn_moisture", "bn_protein"])

    def test_water_tests_count(self):
        water = _catalog_tests_for_category(CATEGORY_WATER)
        assert len(water) == 11
        assert {t.key for t in water} == set(WATER_TEST_KEYS)

    def test_default_water_bundle(self):
        assert default_test_keys_for_category(CATEGORY_WATER) == WATER_TEST_KEYS
        assert default_test_keys_for_category(CATEGORY_FOOD) == []

    def test_micro_tests_count(self):
        from services.protocols.test_catalog import CATEGORY_MICRO, MICRO_TEST_KEYS

        micro = _catalog_tests_for_category(CATEGORY_MICRO)
        assert len(micro) == 6
        assert {t.key for t in micro} == set(MICRO_TEST_KEYS)
        assert default_test_keys_for_category(CATEGORY_MICRO) == MICRO_TEST_KEYS

    def test_cattle_feed_empty(self):
        from services.protocols.test_catalog import (
            CATEGORY_CATTLE_FEED_FERTILIZER,
            list_tests_for_select,
        )

        assert _catalog_tests_for_category(CATEGORY_CATTLE_FEED_FERTILIZER) == []
        assert list_tests_for_select(CATEGORY_CATTLE_FEED_FERTILIZER) == []

    def test_list_tests_for_select_food_filtered(self):
        from services.protocols.test_catalog import CATEGORY_FOOD, list_tests_for_select

        options = list_tests_for_select(CATEGORY_FOOD)
        assert len(options) == 21
        labels = [lbl for _, lbl in options]
        assert not any("[Jaggery]" in lbl for lbl in labels)
        assert not any("[Basic Nutrition]" in lbl for lbl in labels)
        assert not any("[Custom]" in lbl for lbl in labels)
        assert any("Protein" in lbl and "IS 7219" in lbl for lbl in labels)

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
        assert filter_keys_for_category(["ph", "tds"], CATEGORY_WATER) == ["ph", "tds"]
        assert filter_keys_for_category(["ph", "moisture"], CATEGORY_FOOD) == ["moisture"]

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_test("not_a_real_test")

    def test_invalid_numeric_raises(self):
        with pytest.raises((ValueError, TypeError)):
            get_test("moisture").calculate(
                {"w1": "abc", "w2": 10.2, "w": 5.0},
                {},
            )
