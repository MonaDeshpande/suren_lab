"""Unit tests for per-sample analyst assignment scoping."""

from __future__ import annotations

from services.auth import AuthUser
from services.requests import SampleRow, validate_request
from services.samples import sample_scope_for_user
from tests.unit.test_validation import _valid_request


def _user(*roles: str, user_id: int = 1) -> AuthUser:
    return AuthUser(
        id=user_id,
        username="qa_user",
        full_name="QA User",
        roles=roles,
        is_active=True,
        must_change_password=False,
    )


class TestSampleScopeForUser:
    def test_pure_analyst_scoped(self):
        user = _user("analyst", user_id=5)
        assert sample_scope_for_user(user) == (5, True)

    def test_admin_not_scoped(self):
        user = _user("admin")
        assert sample_scope_for_user(user) == (None, False)

    def test_reviewer_not_scoped(self):
        user = _user("reviewer")
        assert sample_scope_for_user(user) == (None, False)

    def test_reception_not_scoped(self):
        user = _user("reception")
        assert sample_scope_for_user(user) == (None, False)

    def test_dual_reception_analyst_not_scoped(self):
        user = _user("reception", "analyst", user_id=7)
        assert sample_scope_for_user(user) == (None, False)


class TestValidateAnalystAssignment:
    def test_missing_analyst_fails(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    test_keys=["moisture"],
                    sample_code="SLS-260717-0001",
                )
            ]
        )
        errors = validate_request(data)
        assert any("assign a chemical analyst" in e.lower() for e in errors)

    def test_with_analyst_passes_validation(self):
        assert validate_request(_valid_request()) == []
