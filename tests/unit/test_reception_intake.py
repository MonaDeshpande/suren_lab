"""Unit tests for Reception intake helpers (mode change, package gate)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.protocols.test_catalog import CATEGORY_FOOD, CATEGORY_WATER
from ui.components import (
    RECEPTION_MODE_EDIT,
    RECEPTION_MODE_NEW,
    RECEPTION_MODE_PACKAGES,
    food_intake_packages_ready,
    handle_reception_mode_change,
    should_clear_ctr_form_on_mode_change,
)


class TestShouldClearCtrFormOnModeChange:
    def test_new_to_packages_does_not_clear(self):
        assert (
            should_clear_ctr_form_on_mode_change(
                RECEPTION_MODE_NEW, RECEPTION_MODE_PACKAGES
            )
            is False
        )

    def test_packages_to_new_does_not_clear(self):
        assert (
            should_clear_ctr_form_on_mode_change(
                RECEPTION_MODE_PACKAGES, RECEPTION_MODE_NEW
            )
            is False
        )

    def test_new_to_edit_clears(self):
        assert (
            should_clear_ctr_form_on_mode_change(
                RECEPTION_MODE_NEW, RECEPTION_MODE_EDIT
            )
            is True
        )

    def test_edit_to_new_clears(self):
        assert (
            should_clear_ctr_form_on_mode_change(
                RECEPTION_MODE_EDIT, RECEPTION_MODE_NEW
            )
            is True
        )

    def test_packages_to_edit_does_not_clear(self):
        assert (
            should_clear_ctr_form_on_mode_change(
                RECEPTION_MODE_PACKAGES, RECEPTION_MODE_EDIT
            )
            is False
        )


class TestHandleReceptionModeChange:
    @pytest.fixture
    def session_state(self):
        state = {
            "reception_mode": RECEPTION_MODE_NEW,
            "_reception_mode_last": RECEPTION_MODE_NEW,
        }
        with patch("ui.components.st") as mock_st:
            mock_st.session_state = state
            yield state, mock_st

    def test_switching_to_packages_preserves_form(self, session_state):
        state, _mock_st = session_state
        state["reception_mode"] = RECEPTION_MODE_PACKAGES
        state["_reception_mode_last"] = RECEPTION_MODE_NEW

        with patch("ui.components.clear_ctr_form_state") as clear_mock:
            handle_reception_mode_change()

        clear_mock.assert_not_called()
        assert state["_reception_mode_last"] == RECEPTION_MODE_PACKAGES

    def test_switching_new_to_edit_clears_form(self, session_state):
        state, _mock_st = session_state
        state["reception_mode"] = RECEPTION_MODE_EDIT
        state["_reception_mode_last"] = RECEPTION_MODE_NEW

        with patch("ui.components.clear_ctr_form_state") as clear_mock:
            handle_reception_mode_change()

        clear_mock.assert_called_once()
        assert state["_reception_mode_last"] == RECEPTION_MODE_EDIT


class TestFoodIntakePackagesReady:
    def test_non_food_always_ready(self):
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Tap water"}],
            CATEGORY_WATER,
        )
        assert ready is True
        assert blocked == []

    def test_no_named_rows_not_ready(self):
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": ""}],
            CATEGORY_FOOD,
        )
        assert ready is False
        assert blocked == ["Enter at least one sample product name in the table below"]

    def test_defined_package_ready(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {"status": "defined"},
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Jaggery"}],
            CATEGORY_FOOD,
        )
        assert ready is True
        assert blocked == []

    def test_not_defined_blocked(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {"status": "not_defined"},
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Jaggery"}],
            CATEGORY_FOOD,
        )
        assert ready is False
        assert any("Jaggery" in item for item in blocked)

    def test_inactive_blocked(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {"status": "inactive"},
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Jaggery"}],
            CATEGORY_FOOD,
        )
        assert ready is False
        assert any("inactive" in item for item in blocked)

    def test_ambiguous_requires_type_selection(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {"status": "ambiguous"},
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Masala"}],
            CATEGORY_FOOD,
            session={},
        )
        assert ready is False
        assert any("select test package type" in item for item in blocked)

    def test_duplicate_blocked(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {
                "status": "duplicate",
                "duplicate_package_ids": [44, 45],
            },
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Goda Masala"}],
            CATEGORY_FOOD,
        )
        assert ready is False
        assert any("duplicate" in item.lower() for item in blocked)

    def test_ambiguous_with_selection_ready(self, monkeypatch):
        monkeypatch.setattr(
            "services.test_packages.describe_sample_package_for_product",
            lambda name, **kw: {"status": "ambiguous"},
        )
        ready, blocked = food_intake_packages_ready(
            [{"Sr. No": 1, "Name of sample": "Masala"}],
            CATEGORY_FOOD,
            session={"test_package_type_1": "FSSAI"},
        )
        assert ready is True
        assert blocked == []


class TestIntakeTestLabelScopes:
    def test_separate_wl_and_nwl_option_lists(self):
        from types import SimpleNamespace

        from ui.components import _intake_test_label_options

        resolved = SimpleNamespace(
            test_keys_with_logo=["moisture", "total_ash"],
            test_keys_without_logo=["appearance"],
            test_keys=["moisture", "total_ash", "appearance"],
        )
        wl_labels, wl_map = _intake_test_label_options(list(resolved.test_keys_with_logo))
        nwl_labels, nwl_map = _intake_test_label_options(
            list(resolved.test_keys_without_logo)
        )
        assert len(wl_labels) == 2
        assert len(nwl_labels) == 1
        assert wl_map[wl_labels[0]] in resolved.test_keys_with_logo
        assert nwl_map[nwl_labels[0]] in resolved.test_keys_without_logo
