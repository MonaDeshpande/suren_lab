"""
Unit tests for multi-role validation (services/users.py).
"""

from __future__ import annotations

import pytest

from services.users import validate_roles


class TestValidateRoles:
    def test_single_staff_role(self):
        assert validate_roles(["reception"]) == ("reception",)

    def test_two_staff_roles(self):
        assert validate_roles(["reception", "analyst"]) == (
            "reception",
            "analyst",
        )

    def test_admin_exclusive(self):
        with pytest.raises(ValueError, match="cannot be combined"):
            validate_roles(["admin", "reception"])

    def test_admin_alone(self):
        assert validate_roles(["admin"]) == ("admin",)

    def test_max_two_roles(self):
        with pytest.raises(ValueError, match="at most 2"):
            validate_roles(["reception", "analyst", "reviewer"])

    def test_empty_roles(self):
        with pytest.raises(ValueError, match="At least one role"):
            validate_roles([])

    def test_invalid_role(self):
        with pytest.raises(ValueError, match="Invalid role"):
            validate_roles(["supervisor"])

    def test_deduplicates_roles(self):
        assert validate_roles(["analyst", "analyst"]) == ("analyst",)
