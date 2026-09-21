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
    config.addinivalue_line(
        "markers",
        "e2e: demo full-flow scenarios; excluded from run_tests.bat",
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


# ---------------------------------------------------------------------------
# Integration DB fixtures (shared by test_db_integration / test_report_preview)
# ---------------------------------------------------------------------------

_ANALYST_PW = "Temp@12"


def cleanup_test_data(
    *,
    gst: str | None = None,
    appearance_ids: list[int] | None = None,
) -> None:
    """Remove integration test rows; safe to call multiple times."""
    from db.connection import get_db

    normalized_gst = (gst or "").strip().upper()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                if appearance_ids:
                    cur.execute(
                        "DELETE FROM appearance_master WHERE id = ANY(%s)",
                        (appearance_ids,),
                    )
                if normalized_gst:
                    cur.execute(
                        """
                        DELETE FROM test_requests
                         WHERE customer_id IN (
                            SELECT id FROM customers WHERE gst_number = %s
                         )
                        """,
                        (normalized_gst,),
                    )
                    cur.execute(
                        "DELETE FROM customers WHERE gst_number = %s",
                        (normalized_gst,),
                    )
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def qa_analyst_pair(require_db):
    """Two active analyst users for assignment tests."""
    import uuid

    from db.connection import get_db
    from services.users import create_user

    created = []
    for suffix in ("a", "b"):
        user = create_user(
            username=f"qa_db_{suffix}_{uuid.uuid4().hex[:8]}",
            temporary_password=_ANALYST_PW,
            roles=["analyst"],
            full_name=f"QA DB Analyst {suffix.upper()}",
        )
        created.append(user)
    yield created[0], created[1]
    with get_db() as conn:
        with conn.cursor() as cur:
            ids = [u.id for u in created]
            cur.execute("DELETE FROM user_roles WHERE user_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))


@pytest.fixture
def db_test_gst():
    """Unique GST per test; teardown removes customer + requests."""
    import uuid

    gst = f"99DB{uuid.uuid4().hex[:8].upper()}000A1Z5"
    yield gst
    cleanup_test_data(gst=gst)


@pytest.fixture
def appearance_test_cleanup():
    """Track appearance_master rows created in a test for teardown."""
    created_ids: list[int] = []
    yield created_ids
    cleanup_test_data(appearance_ids=created_ids)
