"""Generate Installation Qualification (IQ) protocol Word draft."""

from __future__ import annotations

from pathlib import Path

from validation.docx_util import (
    add_bullets,
    add_cover,
    add_heading,
    add_para,
    add_signature_block,
    add_table,
    dated_filename,
    new_document,
    save_document,
)
from validation.inventory import SYSTEM_NAME, SystemInventory


def write_iq(inv: SystemInventory, out_dir: Path, stamp: str) -> Path:
    doc = new_document()
    add_cover(
        doc,
        doc_title="Installation Qualification (IQ) Protocol",
        doc_code="SLS-VAL-IQ",
        generated_at=inv.generated_at,
    )

    add_heading(doc, "1. Purpose", level=1)
    add_para(
        doc,
        f"Verify that the {SYSTEM_NAME} and its supporting components "
        "are installed and configured correctly in the target environment.",
    )

    add_heading(doc, "2. Scope", level=1)
    add_para(
        doc,
        "Covers Python runtime, Python dependencies, PostgreSQL via Docker, "
        "environment variables, database schema/migrations, admin seed, and "
        "application launch smoke check. Does not cover laboratory instruments.",
    )

    add_heading(doc, "3. System components (from inventory)", level=1)
    add_para(doc, f"Docker image: {inv.docker_image or 'not found'}")
    add_para(doc, f"Host DB port: {inv.docker_host_port or 'not found'}")
    add_para(doc, "Environment keys (.env.example):")
    add_bullets(doc, inv.env_keys or ["(none)"])
    add_para(doc, "Python dependencies (requirements.txt):")
    add_bullets(doc, inv.dependencies or ["(none)"])
    add_para(doc, "Scripts:")
    add_bullets(doc, inv.scripts or ["(none)"])
    add_para(doc, "Migrations:")
    add_bullets(doc, inv.migrations or ["(none)"])
    add_para(doc, "Database tables:")
    add_bullets(doc, [t.name for t in inv.tables] or ["(none)"])

    add_heading(doc, "4. Installation checklist", level=1)
    add_para(
        doc,
        "Executor records Pass / Fail / N/A and initials. Leave Result blank until executed.",
    )

    checks: list[tuple[str, str, str]] = [
        ("IQ-001", "Windows 10+ workstation with Python 3 installed and on PATH", "OS / Python"),
        ("IQ-002", "Microsoft Word available if CTR/Protocol Word→PDF (docx2pdf) path is used", "docx2pdf"),
        ("IQ-003", "Docker Desktop installed and running", "Docker"),
        ("IQ-004", f"Repository present; docker compose uses image {inv.docker_image or 'postgres'}", "Compose"),
        (
            "IQ-005",
            f"PostgreSQL container reachable on host port {inv.docker_host_port or '5433'}",
            "DB port",
        ),
        ("IQ-006", "Copy .env.example to .env; keys configured: " + ", ".join(inv.env_keys), ".env"),
        ("IQ-007", "pip install -r requirements.txt completes without error", "Dependencies"),
    ]
    for dep in inv.dependencies:
        checks.append(
            (
                f"IQ-DEP-{dep.split('>=')[0].split('==')[0].strip()}",
                f"Package installed: {dep}",
                "pip",
            )
        )
    checks.extend(
        [
            ("IQ-008", "docker compose up -d starts sls_lab_db successfully", "DB start"),
            ("IQ-009", "db/schema.sql applied (fresh volume) or migrations applied on existing DB", "Schema"),
        ]
    )
    for mig in inv.migrations:
        checks.append((f"IQ-MIG-{mig}", f"Migration applied if needed: scripts/{mig}", "Migration"))
    checks.extend(
        [
            ("IQ-010", "python scripts/seed_admin.py creates/verifies default admin", "Seed"),
            ("IQ-011", "run_app.bat (or streamlit run app.py) opens http://localhost:8501", "App start"),
            ("IQ-012", "Login page visible; database SELECT 1 succeeds via docker exec", "Smoke"),
            ("IQ-013", "Project folders writable for generated PDF/DOCX downloads", "Permissions"),
            ("IQ-014", "reference/ templates present if Word fill path is used for CTR/protocol", "Templates"),
        ]
    )

    add_table(
        doc,
        ("Check ID", "Verification step", "Category", "Result (P/F/N/A)", "Initials", "Date", "Comments"),
        [(c[0], c[1], c[2], "", "", "", "") for c in checks],
    )

    add_heading(doc, "5. Deviations", level=1)
    add_table(
        doc,
        ("Dev #", "Description", "Impact", "Disposition", "Approved by"),
        [("", "", "", "", "")],
    )

    add_signature_block(doc)
    path = out_dir / dated_filename("SLS_IQ", stamp)
    return save_document(doc, path)
