"""Unit tests for auto-sync of derived sample code into verification."""

from __future__ import annotations

from services.requests import sync_verify_sample_code


def test_sync_fills_empty_session_key():
    session: dict = {}
    assert sync_verify_sample_code("SLS-26-001-01", session=session, sr_no=1) == (
        "SLS-26-001-01"
    )
    assert session["verify_sample_code_1"] == "SLS-26-001-01"


def test_sync_does_not_overwrite_existing_without_flag():
    session = {"verify_sample_code_2": "MANUAL-CODE"}
    assert sync_verify_sample_code("SLS-26-002-01", session=session, sr_no=2) == (
        "MANUAL-CODE"
    )
    assert session["verify_sample_code_2"] == "MANUAL-CODE"


def test_sync_overwrites_when_requested():
    session = {"verify_sample_code_3": "OLD"}
    sync_verify_sample_code(
        "SLS-26-003-01",
        session=session,
        sr_no=3,
        overwrite=True,
    )
    assert session["verify_sample_code_3"] == "SLS-26-003-01"


def test_sync_without_session_returns_code():
    assert sync_verify_sample_code("SLS-26-004-01", sr_no=4) == "SLS-26-004-01"
