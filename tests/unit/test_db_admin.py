"""
Unit tests for services/db_admin.py
"""

from __future__ import annotations

import pytest

from services.db_admin import (
    READ_ONLY_TABLES,
    _mask_row,
    _safe_identifier,
    list_tables,
    set_row_active,
)
from services.versions import MIN_EDIT_REASON_LEN


class TestSafeIdentifier:
    def test_valid_table_name(self):
        assert _safe_identifier("customers") == "customers"

    def test_rejects_injection(self):
        with pytest.raises(ValueError, match="Invalid identifier"):
            _safe_identifier("customers; DROP TABLE users")


class TestMaskRow:
    def test_masks_password_hash(self):
        row = {"id": 1, "username": "admin", "password_hash": "secret"}
        masked = _mask_row("users", row)
        assert masked["password_hash"] == "********"
        assert masked["username"] == "admin"

    def test_other_tables_unchanged(self):
        row = {"id": 1, "customer_name": "Acme"}
        assert _mask_row("customers", row) == row


class TestSetRowActiveValidation:
    def test_read_only_table_rejected(self):
        for table in READ_ONLY_TABLES:
            with pytest.raises(ValueError, match="read-only"):
                set_row_active(
                    table,
                    1,
                    False,
                    "x" * MIN_EDIT_REASON_LEN,
                )

    def test_short_edit_reason_rejected(self):
        with pytest.raises(ValueError, match="at least"):
            set_row_active("customers", 1, False, "short")


@pytest.mark.integration
def test_list_tables_includes_all_schema_tables(require_db):
    names = {t["name"] for t in list_tables()}
    expected = {
        "customers",
        "customer_contacts",
        "test_requests",
        "request_samples",
        "sample_protocols",
        "sample_test_results",
        "sample_test_packages",
        "sample_test_package_tests",
        "custom_formulas",
        "custom_formula_inputs",
        "users",
        "user_roles",
        "audit_log",
        "entity_versions",
    }
    assert expected.issubset(names)


@pytest.mark.integration
def test_fetch_rows_masks_user_password(require_db):
    from services.db_admin import fetch_rows

    rows = fetch_rows("users", limit=5)
    for row in rows:
        if "password_hash" in row:
            assert row["password_hash"] == "********"
