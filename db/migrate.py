"""
db/migrate.py
-------------
Apply idempotent SQL migrations so an existing Docker volume stays in sync
with the current code (avoids missing-table login failures).
"""

from __future__ import annotations

from pathlib import Path

from db.connection import get_db

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Order matters: auth before roles; users before versions FK; samples/customers first.
_MIGRATION_FILES = (
    "migrate_samples.sql",
    "migrate_auth.sql",
    "migrate_user_roles.sql",
    "migrate_protocol.sql",
    "migrate_category.sql",
    "migrate_audit.sql",
    "migrate_contacts.sql",
    "migrate_versions.sql",
    "migrate_sample_assignment.sql",
    "migrate_protocol_number.sql",
    "migrate_report_format.sql",
    "migrate_test_packages.sql",
    "migrate_custom_formulas.sql",
    "migrate_custom_formula_validation.sql",
    "migrate_package_logo_scope.sql",
    "migrate_micro_category.sql",
    "migrate_water_micro_analyst.sql",
    "migrate_row_soft_delete.sql",
    "migrate_sample_verification.sql",
    "migrate_catalog_test_specs.sql",
    "migrate_sample_categories.sql",
    "migrate_retention_50_days.sql",
    "migrate_gst_optional.sql",
    "migrate_appearance_master.sql",
    "migrate_sample_request_details.sql",
    "migrate_analysis_date_range.sql",
    "migrate_protocol_disclaimer.sql",
)

_applied = False


def apply_sql_file(path: Path) -> None:
    """Execute one SQL file against the configured database."""
    sql = path.read_text(encoding="utf-8")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def ensure_schema(*, force: bool = False) -> list[str]:
    """
    Apply all known migrate_*.sql scripts (IF NOT EXISTS / safe re-runs).

    Runs once per process unless ``force=True``. Returns names applied this call.
    """
    global _applied
    if _applied and not force:
        return []

    applied: list[str] = []
    for name in _MIGRATION_FILES:
        path = SCRIPTS / name
        if not path.exists():
            continue
        apply_sql_file(path)
        applied.append(name)

    from db.seed_catalog_specs import seed_builtin_specs

    seed_builtin_specs()

    _applied = True
    return applied
