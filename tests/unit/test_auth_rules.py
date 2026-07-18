"""
Unit tests for password hashing and change_password validation rules (TC-AUTH).
"""

from __future__ import annotations

import pytest

from services.auth import change_password, hash_password, verify_password


class TestPasswordHash:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("Secret@123")
        assert hashed != "Secret@123"
        assert verify_password("Secret@123", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("Secret@123")
        assert verify_password("wrong", hashed) is False

    def test_empty_plain_fails(self):
        hashed = hash_password("Secret@123")
        assert verify_password("", hashed) is False

    def test_empty_hash_fails(self):
        assert verify_password("Secret@123", "") is False

    def test_invalid_hash_returns_false(self):
        assert verify_password("Secret@123", "not-a-bcrypt-hash") is False


class TestChangePasswordRules:
    def test_new_password_min_length(self):
        with pytest.raises(ValueError, match="at least 6 characters"):
            change_password(user_id=1, current_password="anything", new_password="12345")

    def test_new_password_whitespace_stripped_for_length(self):
        with pytest.raises(ValueError, match="at least 6 characters"):
            change_password(user_id=1, current_password="anything", new_password="  123  ")
