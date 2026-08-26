"""Unit tests for catalog_test_specs service (cache + limits display)."""

from __future__ import annotations

from services.catalog_specs import (
    CatalogTestSpec,
    clear_spec_cache,
    get_spec,
    list_specs,
    spec_snapshot,
)


def _patch_cache(monkeypatch, rows: list[CatalogTestSpec]) -> None:
    clear_spec_cache()
    monkeypatch.setattr(
        "services.catalog_specs._load_cache",
        lambda: None,
    )
    monkeypatch.setattr(
        "services.catalog_specs._cache_loaded",
        True,
    )
    monkeypatch.setattr(
        "services.catalog_specs._spec_cache",
        {r.test_key: r for r in rows},
    )


class TestCatalogTestSpec:
    def test_limits_display_prefers_limits_text(self):
        spec = CatalogTestSpec(
            test_key="e_coli",
            category="micro",
            test_name="E. Coli",
            limits_text="Shall be Absent",
            limits_desirable="10",
            limits_permissible="20",
        )
        assert spec.limits_display == "Shall be Absent"

    def test_limits_display_joins_water_columns(self):
        spec = CatalogTestSpec(
            test_key="ph",
            category="water",
            test_name="pH",
            limits_desirable="6.5-8.5",
            limits_permissible="6.0-9.0",
        )
        assert spec.limits_display == "6.5-8.5 / 6.0-9.0"

    def test_version_label_marks_latest(self):
        spec = CatalogTestSpec(
            test_key="moisture",
            category="food",
            test_name="Moisture",
            current_version_no=3,
        )
        assert spec.version_label == "v3 · Latest"

    def test_spec_snapshot_includes_version_no(self):
        spec = CatalogTestSpec(
            test_key="e_coli",
            category="micro",
            test_name="E. Coli",
            method_of_analysis="IS 5887",
            current_version_no=2,
        )
        snap = spec_snapshot(spec)
        assert snap["version_no"] == 2
        assert snap["method_of_analysis"] == "IS 5887"


class TestCatalogSpecsCache:
    def test_get_spec_from_cache(self, monkeypatch):
        row = CatalogTestSpec(
            test_key="total_plate_count",
            category="micro",
            test_name="Total Plate Count",
            method_of_analysis="IS:5402:2018",
            limits_text="<5.0 x 10⁴ cfu/g",
            default_unit="cfu/gm",
            unit_editable=False,
            sort_order=1,
            current_version_no=1,
        )
        _patch_cache(monkeypatch, [row])
        assert get_spec("total_plate_count") == row
        assert get_spec("missing") is None

    def test_list_specs_filters_category(self, monkeypatch):
        rows = [
            CatalogTestSpec("moisture", "food", "Moisture"),
            CatalogTestSpec("ph", "water", "pH"),
            CatalogTestSpec("e_coli", "micro", "E. Coli"),
        ]
        _patch_cache(monkeypatch, rows)
        food = list_specs("food")
        assert [s.test_key for s in food] == ["moisture"]
        micro = list_specs("micro")
        assert [s.test_key for s in micro] == ["e_coli"]