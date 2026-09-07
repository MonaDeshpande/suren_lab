"""Sample table session-state helpers used by Reception CTR save."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from ui import components as ui_components


class _SessionState(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def pop(self, key, default=None):
        return super().pop(key, default)


@pytest.fixture
def session_state():
    state = _SessionState()
    with patch.object(ui_components.st, "session_state", state):
        yield state


def _filled_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Sr. No": 1,
                "Name of sample": "Jaggery",
                "Code/batch no.": "05",
                "Sample qty.": "500gm",
                "Parameters": "FSSAI",
                "_sample_id": None,
                "_status": "pending",
            }
        ]
    )


class TestSampleEditorDfForRender:
    def test_merges_pending_batch_and_qty_edits(self, session_state):
        session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY] = pd.DataFrame(
            ui_components._default_sample_rows()
        )
        session_state[ui_components._SAMPLE_EDITOR_WIDGET_KEY] = {
            "edited_rows": {
                0: {"Code/batch no.": "002", "Sample qty.": "100 gm"},
            },
            "added_rows": [],
            "deleted_rows": [],
        }
        out = ui_components._sample_editor_df_for_render()
        assert out.iloc[0]["Code/batch no."] == "002"
        assert out.iloc[0]["Sample qty."] == "100 gm"


class TestPersistSampleEditorState:
    def test_persist_merges_edited_rows_into_live(self, session_state):
        session_state[ui_components._SAMPLE_EDITOR_KEY] = pd.DataFrame(
            ui_components._default_sample_rows()
        )
        session_state[ui_components._SAMPLE_EDITOR_WIDGET_KEY] = {
            "edited_rows": {0: {"Name of sample": "Goda Masala", "Sample qty.": "1kg"}},
            "added_rows": [],
            "deleted_rows": [],
        }
        ui_components.persist_sample_editor_state()
        live = session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY]
        assert live.iloc[0]["Name of sample"] == "Goda Masala"
        assert live.iloc[0]["Sample qty."] == "1kg"

    def test_round_trip_survives_widget_remount(self, session_state):
        filled = _filled_df()
        session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY] = filled
        session_state[ui_components._SAMPLE_EDITOR_KEY] = pd.DataFrame(
            ui_components._default_sample_rows()
        )
        session_state.pop(ui_components._SAMPLE_EDITOR_WIDGET_KEY, None)
        out = ui_components._current_sample_editor_df()
        assert out.iloc[0]["Name of sample"] == "Jaggery"


class TestCurrentSampleEditorDf:
    def test_prefers_live_dataframe_over_empty_stored(self, session_state):
        session_state[ui_components._SAMPLE_EDITOR_KEY] = pd.DataFrame(
            ui_components._default_sample_rows()
        )
        session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY] = _filled_df()
        # Streamlit stores EditingState on the widget key — not a DataFrame.
        session_state[ui_components._SAMPLE_EDITOR_WIDGET_KEY] = {
            "edited_rows": {0: {"Name of sample": "Jaggery"}},
            "added_rows": [],
            "deleted_rows": [],
        }

        out = ui_components._current_sample_editor_df()
        assert out.iloc[0]["Name of sample"] == "Jaggery"
        assert out.iloc[0]["Parameters"] == "FSSAI"

    def test_widget_editing_state_is_not_treated_as_table(self, session_state):
        session_state[ui_components._SAMPLE_EDITOR_KEY] = pd.DataFrame(
            ui_components._default_sample_rows()
        )
        session_state[ui_components._SAMPLE_EDITOR_WIDGET_KEY] = {
            "edited_rows": {},
            "added_rows": [],
            "deleted_rows": [],
        }

        out = ui_components._current_sample_editor_df()
        assert not ui_components._sample_row_nonempty(out.iloc[0].to_dict())

    def test_reset_clears_live_and_widget(self, session_state):
        session_state[ui_components._SAMPLE_EDITOR_WIDGET_KEY] = {"edited_rows": {}}
        session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY] = _filled_df()
        ui_components._reset_sample_editor(_filled_df())
        assert ui_components._SAMPLE_EDITOR_WIDGET_KEY not in session_state
        assert (
            session_state[ui_components._SAMPLE_EDITOR_LIVE_KEY].iloc[0]["Name of sample"]
            == "Jaggery"
        )
