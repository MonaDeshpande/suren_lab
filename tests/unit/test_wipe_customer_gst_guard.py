"""GST allowlist for scripts/wipe_customer_by_gst.py — no real client GSTINs."""

from __future__ import annotations

import pytest

from scripts.wipe_customer_by_gst import (
    _GST_GUARD_MESSAGE,
    is_deletable_test_gst,
    wipe_customer_by_gst,
)


@pytest.mark.parametrize(
    "gst",
    [
        "99MANUAL0001A1Z5",
        "99DBABCDEF12000A1Z5",
        "99TESTQA0000A1Z5",
        "99A1B2C3D4E5F6G7H1Z5",
    ],
)
def test_is_deletable_test_gst_accepts_dummy_patterns(gst: str) -> None:
    assert is_deletable_test_gst(gst) is True


@pytest.mark.parametrize(
    "gst",
    [
        "27AAAAA0000A1Z5",
        "27AABCU9603R1ZM",
        "MANUAL0001A1Z5",
        "991Z5",
    ],
)
def test_is_deletable_test_gst_rejects_real_or_invalid(gst: str) -> None:
    assert is_deletable_test_gst(gst) is False


def test_wipe_customer_by_gst_rejects_client_gst_without_db() -> None:
    with pytest.raises(ValueError, match="Refusing to delete"):
        wipe_customer_by_gst(gst="27AAAAA0000A1Z5", dry_run=True)


def test_guard_message_is_documented() -> None:
    assert "99MANUAL" in _GST_GUARD_MESSAGE
