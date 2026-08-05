"""Unit tests for edit-reason validation and version helpers."""

from __future__ import annotations

import pytest

from services.versions import MIN_EDIT_REASON_LEN, validate_edit_reason


class TestValidateEditReason:
    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="required"):
            validate_edit_reason("")

    def test_whitespace_rejected(self):
        with pytest.raises(ValueError, match="required"):
            validate_edit_reason("   ")

    def test_too_short_rejected(self):
        with pytest.raises(ValueError, match=str(MIN_EDIT_REASON_LEN)):
            validate_edit_reason("too short")

    def test_valid_reason(self):
        validate_edit_reason("Corrected customer address on request")

    def test_strips_whitespace(self):
        validate_edit_reason("  " + "x" * MIN_EDIT_REASON_LEN + "  ")
