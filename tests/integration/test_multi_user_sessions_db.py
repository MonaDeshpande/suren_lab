"""
Integration tests for multi-user login (concurrent auth + session refresh).

Maps to TC-AUTH-013…015. Requires live PostgreSQL.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from services.auth import (
    authenticate,
    is_logged_in,
    refresh_session_from_db,
    set_session_user,
)
from services.users import create_user, set_active

pytestmark = pytest.mark.integration

_PREFIX = "qa_multi_"
_TEMP_PW = "Temp@12"


def _uname(suffix: str) -> str:
    return f"{_PREFIX}{suffix}_{uuid.uuid4().hex[:8]}"


def _delete_qa_users() -> None:
    from db.connection import get_db

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE username LIKE %s",
                (f"{_PREFIX}%",),
            )
            ids = [r[0] for r in cur.fetchall()]
            if not ids:
                return
            cur.execute("DELETE FROM user_roles WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))


class _SessionState(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def pop(self, key, default=None):
        return super().pop(key, default)


@pytest.fixture
def qa_multi_users(require_db):
    _delete_qa_users()
    yield
    _delete_qa_users()


def test_two_users_authenticate_at_same_time(qa_multi_users):
    """Different accounts can authenticate independently (TC-AUTH-013)."""
    u1 = create_user(
        username=_uname("rec"),
        temporary_password=_TEMP_PW,
        roles=["reception"],
        full_name="QA Reception",
    )
    u2 = create_user(
        username=_uname("ana"),
        temporary_password=_TEMP_PW,
        roles=["analyst"],
        full_name="QA Analyst",
    )
    a1 = authenticate(u1.username, _TEMP_PW)
    a2 = authenticate(u2.username, _TEMP_PW)
    assert a1 is not None
    assert a2 is not None
    assert a1.id != a2.id
    assert a1.roles == ("reception",)
    assert a2.roles == ("analyst",)


def test_same_user_can_authenticate_twice(qa_multi_users):
    """No duplicate-login block — same credentials succeed twice (TC-AUTH-014)."""
    user = create_user(
        username=_uname("dual"),
        temporary_password=_TEMP_PW,
        roles=["analyst"],
        full_name="QA Dual",
    )
    first = authenticate(user.username, _TEMP_PW)
    second = authenticate(user.username, _TEMP_PW)
    assert first is not None
    assert second is not None
    assert first.id == second.id


def test_refresh_session_clears_deactivated_user(qa_multi_users):
    """Deactivated user loses session on next DB refresh (TC-AUTH-015)."""
    from services.auth import get_user_by_id

    user = create_user(
        username=_uname("off"),
        temporary_password=_TEMP_PW,
        roles=["reception"],
        full_name="QA Off",
    )
    auth_user = authenticate(user.username, _TEMP_PW)
    assert auth_user is not None

    state = _SessionState()
    with patch("services.auth.st.session_state", state):
        set_session_user(auth_user)
        assert is_logged_in() is True

        set_active(user.id, False, actor=None)
        refreshed = refresh_session_from_db()
        assert refreshed is None
        assert is_logged_in() is False

        # Re-activate so cleanup can proceed; verify login works again
        set_active(user.id, True, actor=None)
        again = get_user_by_id(user.id)
        assert again is not None and again.is_active
