"""Unit tests for workspace page access rules."""

from __future__ import annotations

from services.auth import AuthUser
from ui.auth import PAGE_ACCESS, user_can_access_page


def _user(*roles: str) -> AuthUser:
    return AuthUser(
        id=1,
        username="qa_user",
        full_name="QA User",
        roles=roles,
        is_active=True,
        must_change_password=False,
    )


class TestUserCanAccessPage:
    def test_pure_analyst_only_analyst_workspace(self):
        user = _user("analyst")
        assert user_can_access_page(user, "analyst") is True
        assert user_can_access_page(user, "reception") is False
        assert user_can_access_page(user, "reviewer") is False
        assert user_can_access_page(user, "admin") is False

    def test_pure_reviewer_only_reviewer_workspace(self):
        user = _user("reviewer")
        assert user_can_access_page(user, "reviewer") is True
        assert user_can_access_page(user, "reception") is False
        assert user_can_access_page(user, "analyst") is False
        assert user_can_access_page(user, "admin") is False

    def test_pure_reception_only_reception_workspace(self):
        user = _user("reception")
        assert user_can_access_page(user, "reception") is True
        assert user_can_access_page(user, "analyst") is False
        assert user_can_access_page(user, "reviewer") is False
        assert user_can_access_page(user, "admin") is False

    def test_dual_reception_analyst_sees_both(self):
        user = _user("reception", "analyst")
        assert user_can_access_page(user, "reception") is True
        assert user_can_access_page(user, "analyst") is True
        assert user_can_access_page(user, "reviewer") is False
        assert user_can_access_page(user, "admin") is False

    def test_admin_sees_all_workspaces(self):
        user = _user("admin")
        for page in PAGE_ACCESS:
            assert user_can_access_page(user, page) is True

    def test_unknown_page_denied(self):
        user = _user("admin")
        assert user_can_access_page(user, "unknown") is False
