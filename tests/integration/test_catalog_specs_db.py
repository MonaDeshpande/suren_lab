"""Integration tests for catalog_test_specs seed and Admin updates."""

from __future__ import annotations

import pytest

from db.migrate import ensure_schema
from services.catalog_specs import (
    clear_spec_cache,
    get_spec,
    list_spec_versions,
    list_specs,
    update_spec,
)
from services.protocols.test_catalog import MICRO_TEST_KEYS

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    yield
    clear_spec_cache()


class TestCatalogSpecsDb:
    def test_seed_includes_micro_panel(self, require_db):
        ensure_schema(force=True)
        clear_spec_cache()
        micro = list_specs("micro")
        assert len(micro) == 6
        assert {s.test_key for s in micro} == set(MICRO_TEST_KEYS)

    def test_tpc_has_fixed_cfu_unit(self, require_db):
        ensure_schema(force=True)
        clear_spec_cache()
        spec = get_spec("total_plate_count")
        assert spec is not None
        assert spec.default_unit == "cfu/gm"
        assert spec.unit_editable is False
        assert spec.current_version_no == 1

    def test_admin_update_creates_new_version(self, require_db):
        ensure_schema(force=True)
        clear_spec_cache()
        key = "e_coli"
        before = get_spec(key)
        assert before is not None
        prior_versions = len(list_spec_versions(key, limit=20))

        updated = update_spec(
            key,
            test_name=before.test_name,
            method_of_analysis="Updated method for integration test",
            limits_text=before.limits_text,
            limits_desirable=before.limits_desirable,
            limits_permissible=before.limits_permissible,
            default_unit=before.default_unit,
            unit_editable=before.unit_editable,
            sort_order=before.sort_order,
            edit_reason="Integration test version bump",
            actor=None,
        )
        assert updated.method_of_analysis == "Updated method for integration test"
        assert updated.current_version_no == before.current_version_no + 1

        clear_spec_cache()
        live = get_spec(key)
        assert live is not None
        assert live.current_version_no == updated.current_version_no
        assert live.method_of_analysis == "Updated method for integration test"

        versions = list_spec_versions(key, limit=20)
        assert len(versions) == prior_versions + 1
        archived = versions[0].snapshot()
        assert archived.get("version_no") == before.current_version_no
        assert archived.get("method_of_analysis") == before.method_of_analysis
