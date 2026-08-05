"""Unit tests for per-browser session helpers (multi-user isolation)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.auth import (
    AuthUser,
    clear_session_user,
    get_session_user,
    is_logged_in,
    set_session_user,
)


class _SessionState(dict):
    """Minimal stand-in for Streamlit session_state."""

    def get(self, key, default=None):
        return super().get(key, default)

    def pop(self, key, default=None):
        return super().pop(key, default)


@pytest.fixture
def session_state():
    state = _SessionState()
    with patch("services.auth.st.session_state", state):
        yield state


def _sample_user(**kwargs) -> AuthUser:
    defaults = {
        "id": 42,
        "username": "analyst1",
        "full_name": "Analyst One",
        "roles": ("analyst",),
        "is_active": True,
        "must_change_password": False,
    }
    defaults.update(kwargs)
    return AuthUser(**defaults)


class TestSessionHelpers:
    def test_set_session_user_populates_keys(self, session_state):
        user = _sample_user()
        set_session_user(user)
        assert session_state["user_id"] == 42
        assert session_state["username"] == "analyst1"
        assert session_state["roles"] == ["analyst"]
        assert session_state["full_name"] == "Analyst One"
        assert session_state["must_change_password"] is False

    def test_is_logged_in_after_set(self, session_state):
        assert is_logged_in() is False
        set_session_user(_sample_user())
        assert is_logged_in() is True

    def test_get_session_user_roundtrip(self, session_state):
        set_session_user(_sample_user(roles=("reception", "analyst")))
        restored = get_session_user()
        assert restored is not None
        assert restored.id == 42
        assert restored.username == "analyst1"
        assert restored.roles == ("reception", "analyst")

    def test_clear_session_user_removes_auth_keys(self, session_state):
        set_session_user(_sample_user())
        session_state["role"] = "analyst"  # legacy key
        clear_session_user()
        assert is_logged_in() is False
        assert get_session_user() is None
        assert "role" not in session_state

    def test_sessions_are_independent_per_browser(self):
        """Two isolated session dicts model different machines/browsers."""
        state_a = _SessionState()
        state_b = _SessionState()

        with patch("services.auth.st.session_state", state_a):
            set_session_user(_sample_user(id=1, username="reception1", roles=("reception",)))
            assert is_logged_in() is True

        with patch("services.auth.st.session_state", state_b):
            assert is_logged_in() is False
            set_session_user(_sample_user(id=2, username="analyst1", roles=("analyst",)))
            assert get_session_user().username == "analyst1"

        with patch("services.auth.st.session_state", state_a):
            assert get_session_user().username == "reception1"
