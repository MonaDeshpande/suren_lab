"""
Pytest configuration and shared fixtures for SLS Lab.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Project root on sys.path so `services`, `db`, `ui` import cleanly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that require a live PostgreSQL (Docker) database",
    )


@pytest.fixture(scope="session")
def db_available() -> bool:
    """True when Postgres accepts a connection."""
    try:
        from db.connection import test_connection

        ok, _ = test_connection()
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def require_db(db_available: bool) -> None:
    if not db_available:
        pytest.skip("PostgreSQL not available — start docker compose to run integration tests")
