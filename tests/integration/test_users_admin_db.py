"""
Integration tests for admin user management (create / roles / activate / reset).

Maps to TC-ADM-001…002, 007b–c, 008…012, 019–020 and TC-E2E-009.
Requires live PostgreSQL (docker compose).

Run: pytest tests/integration/test_users_admin_db.py -q
"""

from __future__ import annotations

import uuid

import pytest

from db.connection import get_db
from services.auth import authenticate, get_user_by_username, verify_password
from services.users import (
    create_user,
    get_user_roles,
    list_users,
    reset_password,
    set_active,
    set_roles,
)

pytestmark = pytest.mark.integration

_PREFIX = "qa_adm_"
_TEMP_PW = "Temp@12"


def _uname(suffix: str) -> str:
    return f"{_PREFIX}{suffix}_{uuid.uuid4().hex[:8]}"


def _delete_qa_users() -> None:
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


@pytest.fixture
def qa_users(require_db):
    """Create/cleanup namespace for qa_adm_* users."""
    _delete_qa_users()
    yield
    _delete_qa_users()


def _active_admins() -> list:
    return [
        u
        for u in list_users()
        if u.is_active and "admin" in u.roles
    ]


def test_create_users_for_each_staff_role(qa_users):
    created = []
    for role in ("reception", "analyst", "reviewer"):
        user = create_user(
            username=_uname(role[:3]),
            temporary_password=_TEMP_PW,
            roles=[role],
            full_name=f"QA {role}",
        )
        created.append(user)
        assert user.is_active is True
        assert user.must_change_password is True
        assert user.roles == (role,)
        assert get_user_roles(user.id) == (role,)
        auth = authenticate(user.username, _TEMP_PW)
        assert auth is not None
        assert auth.has_role(role)


def test_set_roles_two_staff_roles(qa_users):
    user = create_user(
        username=_uname("dual"),
        temporary_password=_TEMP_PW,
        roles=["reception"],
    )
    set_roles(user.id, ["reception", "analyst"])
    roles = get_user_roles(user.id)
    assert set(roles) == {"reception", "analyst"}
    auth = authenticate(user.username, _TEMP_PW)
    assert auth is not None
    assert auth.has_any_role("reception", "analyst")


def test_set_roles_admin_exclusive_rejected(qa_users):
    user = create_user(
        username=_uname("excl"),
        temporary_password=_TEMP_PW,
        roles=["reception"],
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        set_roles(user.id, ["admin", "reception"])
    assert get_user_roles(user.id) == ("reception",)


def test_deactivate_and_reactivate_staff(qa_users):
    user = create_user(
        username=_uname("deact"),
        temporary_password=_TEMP_PW,
        roles=["analyst"],
    )
    set_active(user.id, False)
    assert authenticate(user.username, _TEMP_PW) is None

    set_active(user.id, True)
    auth = authenticate(user.username, _TEMP_PW)
    assert auth is not None
    assert auth.is_active is True


def test_cannot_deactivate_last_active_admin(qa_users):
    # Drop any leftover qa_adm_* admins so bootstrap (or one remaining) is sole.
    for u in list_users():
        if u.username.startswith(_PREFIX) and "admin" in u.roles and u.is_active:
            set_active(u.id, False)

    admins = _active_admins()
    assert len(admins) >= 1
    if len(admins) > 1:
        pytest.skip("Multiple non-qa admins present; cannot isolate last-admin case")

    sole = admins[0]
    with pytest.raises(ValueError, match="last active admin"):
        set_active(sole.id, False)
    still = get_user_by_username(sole.username)
    assert still is not None and still.is_active is True


def test_cannot_demote_last_active_admin(qa_users):
    for u in list_users():
        if u.username.startswith(_PREFIX) and "admin" in u.roles and u.is_active:
            set_active(u.id, False)

    admins = _active_admins()
    assert len(admins) >= 1
    if len(admins) > 1:
        pytest.skip("Multiple non-qa admins present; cannot isolate last-admin case")

    sole = admins[0]
    with pytest.raises(ValueError, match="last active admin"):
        set_roles(sole.id, ["reception"])
    assert "admin" in get_user_roles(sole.id)


def test_second_admin_can_be_deactivated(qa_users):
    second = create_user(
        username=_uname("admin2"),
        temporary_password=_TEMP_PW,
        roles=["admin"],
        full_name="QA Second Admin",
    )
    assert len(_active_admins()) >= 2

    set_active(second.id, False)
    assert authenticate(second.username, _TEMP_PW) is None

    remaining = _active_admins()
    assert len(remaining) >= 1
    assert all(u.id != second.id for u in remaining)


def test_reset_password_sets_must_change(qa_users):
    user = create_user(
        username=_uname("rst"),
        temporary_password=_TEMP_PW,
        roles=["reviewer"],
    )
    new_temp = "Reset@99"
    reset_password(user.id, new_temp)

    refreshed = next(u for u in list_users() if u.id == user.id)
    assert refreshed.must_change_password is True
    assert authenticate(user.username, _TEMP_PW) is None
    auth = authenticate(user.username, new_temp)
    assert auth is not None
    assert auth.must_change_password is True

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE id = %s",
                (user.id,),
            )
            row = cur.fetchone()
    assert row is not None
    assert verify_password(new_temp, row[0]) is True
