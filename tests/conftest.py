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
    from db.migrate import ensure_schema

    ensure_schema()


@pytest.fixture(autouse=True)
def _mock_resolve_package_for_unit_tests(request, monkeypatch):
    """Fake package resolution in unit tests (integration tests use real DB)."""
    if request.node.get_closest_marker("integration"):
        return

    from services.protocols.test_catalog import normalize_category, CATEGORY_FOOD
    from services.test_packages import (
        ResolvedPackage,
        normalize_package_type,
        package_display_label,
    )

    def fake_resolve(
        sample_product_name: str,
        package_type: str,
        *,
        category: str = CATEGORY_FOOD,
    ):
        if normalize_category(category) != CATEGORY_FOOD:
            return None
        ptype = normalize_package_type(package_type)
        name = (sample_product_name or "").strip()
        if not name or not ptype:
            return None
        if name.lower() == "missingpackage":
            return None
        keys = ["moisture"]
        if name.lower() == "mixed":
            keys = ["moisture", "bn_protein"]
        return ResolvedPackage(
            package_id=99,
            package_version_no=1,
            package_type=ptype,
            sample_product_name=name,
            test_keys=keys,
            display_label=package_display_label(name, ptype),
        )

    monkeypatch.setattr("services.requests.resolve_package_tests", fake_resolve)
