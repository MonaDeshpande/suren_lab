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


def sample_verification_kwargs(**overrides) -> dict:
    """Default per-sample verification checklist fields for unit tests."""
    from datetime import date

    base = {
        "verify_review_date": date(2026, 7, 17),
        "verify_lab_code": "SLS/26/306",
        "verify_sample_condition": "Ambient",
        "verify_qty_checked": True,
        "verify_chemical_available": True,
        "verify_methods_available": True,
        "verify_methods_informed": True,
        "verify_tat_informed": True,
        "verify_ready_to_issue": True,
        "verify_conformity_statement": False,
    }
    base.update(overrides)
    return base


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
            test_keys_with_logo=keys,
            test_keys_without_logo=[],
            display_label=package_display_label(name, ptype),
        )

    def fake_resolve_product(
        sample_product_name: str,
        *,
        category: str = CATEGORY_FOOD,
    ):
        if normalize_category(category) != CATEGORY_FOOD:
            return None
        name = (sample_product_name or "").strip()
        if not name:
            return None
        if name.lower() == "missingpackage":
            return None
        keys = ["moisture"]
        if name.lower() == "mixed":
            keys = ["moisture", "bn_protein"]
        ptype = "fssai"
        return ResolvedPackage(
            package_id=99,
            package_version_no=1,
            package_type=ptype,
            sample_product_name=name,
            test_keys=keys,
            test_keys_with_logo=keys,
            test_keys_without_logo=[],
            display_label=package_display_label(name, ptype),
        )

    def fake_describe_product(
        sample_product_name: str,
        *,
        category: str = CATEGORY_FOOD,
    ):
        resolved = fake_resolve_product(sample_product_name, category=category)
        if resolved:
            return {
                "status": "defined",
                "package_id": resolved.package_id,
                "version_no": resolved.package_version_no,
                "display_label": resolved.display_label,
                "is_active": True,
                "active_count": 1,
                "wl_count": len(resolved.test_keys_with_logo),
                "nwl_count": len(resolved.test_keys_without_logo),
                "test_keys": list(resolved.test_keys),
                "test_keys_with_logo": list(resolved.test_keys_with_logo),
                "test_keys_without_logo": list(resolved.test_keys_without_logo),
                "ambiguous_types": [],
            }
        name = (sample_product_name or "").strip()
        if name.lower() == "missingpackage":
            return {
                "status": "not_defined",
                "test_keys": [],
                "ambiguous_types": [],
            }
        return {
            "status": "not_defined",
            "test_keys": [],
            "ambiguous_types": [],
        }

    def fake_describe_package(
        sample_product_name: str,
        package_type: str,
        *,
        category: str = CATEGORY_FOOD,
        **kwargs,
    ):
        resolved = fake_resolve(
            sample_product_name, package_type, category=category
        )
        if resolved:
            return {
                "status": "defined",
                "package_id": resolved.package_id,
                "version_no": resolved.package_version_no,
                "display_label": resolved.display_label,
                "is_active": True,
                "wl_count": len(resolved.test_keys_with_logo),
                "nwl_count": len(resolved.test_keys_without_logo),
                "test_keys_with_logo": list(resolved.test_keys_with_logo),
                "test_keys_without_logo": list(resolved.test_keys_without_logo),
            }
        name = (sample_product_name or "").strip()
        if name.lower() == "missingpackage":
            return {"status": "not_defined"}
        return {"status": "not_defined"}

    monkeypatch.setattr("services.requests.resolve_package_tests", fake_resolve)
    monkeypatch.setattr("services.requests.resolve_package_for_product", fake_resolve_product)
    monkeypatch.setattr(
        "services.test_packages.describe_sample_package",
        fake_describe_package,
    )
    monkeypatch.setattr(
        "services.test_packages.describe_sample_package_for_product",
        fake_describe_product,
    )
