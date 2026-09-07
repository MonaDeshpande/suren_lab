"""Generate URS (User Requirements Specification) Word draft."""

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
from validation.inventory import ORGANIZATION, SYSTEM_NAME, SystemInventory


def _req_rows(inv: SystemInventory) -> list[tuple[str, str, str, str]]:
    """Return (id, category, requirement, source) rows."""
    rows: list[tuple[str, str, str, str]] = []
    counters: dict[str, int] = {}

    def add(cat: str, text: str, source: str) -> None:
        prefix = {
            "Authentication": "AUTH",
            "RBAC": "RBAC",
            "Reception": "REC",
            "Analyst": "ANL",
            "Formulas": "FOR",
            "Reviewer": "REV",
            "Admin": "ADM",
            "Audit": "AUD",
            "Retention": "RET",
            "Documents": "DOC",
            "Data": "DATA",
            "Infrastructure": "INF",
        }.get(cat, "GEN")
        counters[prefix] = counters.get(prefix, 0) + 1
        rows.append((f"URS-{prefix}-{counters[prefix]:03d}", cat, text, source))

    add(
        "Authentication",
        "The system shall authenticate users with username and password; "
        "passwords shall be stored using bcrypt hashes.",
        "services/auth.py",
    )
    add(
        "Authentication",
        "The system shall reject invalid credentials and inactive accounts "
        "with a generic failure message (no user enumeration).",
        "ui/auth.py",
    )
    add(
        "Authentication",
        "Staff accounts created by admin shall be forced to change temporary "
        "password on first login before using workspaces.",
        "ui/auth.py, services/users.py",
    )
    add(
        "RBAC",
        f"The system shall support roles: {', '.join(inv.roles)}. "
        "Each user shall have one or two roles; admin shall not be combined "
        "with other roles.",
        "services/auth.py ROLES",
    )
    for page in inv.pages:
        add(
            "RBAC",
            f"Page {page.filename} ({page.title}) shall be accessible only to "
            f"role(s): {', '.join(page.roles)}.",
            f"pages/{page.filename}",
        )
    add(
        "Reception",
        "Reception shall capture Customer Test Request (CTR) data including "
        "customer details, samples, and tests to perform.",
        "pages/1_Reception.py, services/requests.py",
    )
    add(
        "Reception",
        "Customer master data shall be permanent and upserted by unique GST number.",
        "services/customers.py, db/schema.sql customers",
    )
    add(
        "Reception",
        "Each sample shall receive a unique sample code of format SLS-YYMMDD-NNNN "
        "for analyst handoff.",
        "services/samples.py",
    )
    add(
        "Analyst",
        "Analyst shall open samples by sample code, complete protocol header "
        "and worksheet results, and update sample status.",
        "pages/2_Analyst.py, services/protocol_store.py",
    )
    for test in inv.lab_tests:
        add(
            "Formulas",
            f"Shared catalog test '{test.name}' (key={test.key}) shall compute "
            f"using formula: {test.formula_display or 'as implemented'}. "
            f"Method: {test.method or 'n/a'}; unit: {test.unit or 'n/a'}.",
            "services/protocols/test_catalog.py",
        )
    add(
        "Reviewer",
        "Reviewer shall review reception and analyst data and generate Final "
        "Test Report PDF conforming to QSF 7.8.2 layout, setting status to reported.",
        "pages/3_Reviewer.py, services/test_report_pdf.py",
    )
    add(
        "Admin",
        "Admin shall create users, assign/change roles, activate/deactivate "
        "accounts, and reset temporary passwords, with last-admin protection.",
        "pages/4_Admin.py, services/users.py",
    )
    add(
        "Admin",
        "Admin shall view the audit log of meaningful write actions.",
        "pages/4_Admin.py, services/audit.py",
    )
    add(
        "Reception",
        "When admin, reception, or reviewer edits existing customer master data "
        "or an existing Customer Test Request, the system shall require a written "
        "edit reason, archive the prior state as a version, and retain version history.",
        "services/versions.py, pages/1_Reception.py, pages/4_Admin.py",
    )
    for action in inv.audit_actions:
        add(
            "Audit",
            f"The system shall record audit action '{action}' with user, "
            "timestamp, entity table, and optional entity id/details.",
            "code references to log_from_user",
        )
    add(
        "Retention",
        "Sample rows shall expire after 50 days and be purgeable via app open "
        "cleanup and/or scripts/cleanup_expired_samples.py; customers remain permanent.",
        "services/samples.py, scripts/cleanup_expired_samples.py",
    )
    add(
        "Documents",
        "The system shall generate CTR PDF/DOCX and Analyst protocol PDF/DOCX with "
        "generator stamps (Generated by + date/time), and Final Test Report PDF without "
        "generator stamps on the customer-facing document.",
        "services/pdf_generator.py, docx_filler.py, protocol_*, test_report_pdf.py",
    )
    for table in inv.tables:
        cols = ", ".join(table.columns[:12])
        more = "…" if len(table.columns) > 12 else ""
        add(
            "Data",
            f"Database table '{table.name}' shall persist fields including: {cols}{more}.",
            "db/schema.sql",
        )
    add(
        "Infrastructure",
        f"The application shall run against PostgreSQL "
        f"({inv.docker_image or 'postgres'}) exposed on host port "
        f"{inv.docker_host_port or '5433'}, configured via environment variables: "
        f"{', '.join(inv.env_keys) or 'see .env.example'}.",
        "docker-compose.yml, .env.example",
    )
    return rows


def write_urs(inv: SystemInventory, out_dir: Path, stamp: str) -> Path:
    doc = new_document()
    add_cover(
        doc,
        doc_title="User Requirements Specification (URS)",
        doc_code="SLS-VAL-URS",
        generated_at=inv.generated_at,
    )

    add_heading(doc, "1. Purpose", level=1)
    add_para(
        doc,
        f"This URS defines user requirements for {SYSTEM_NAME} as reverse-engineered "
        "from the as-built codebase (retrospective / as-built specification). "
        "Use it for validation planning, traceability, and change control.",
    )

    add_heading(doc, "2. Scope", level=1)
    add_para(
        doc,
        "In scope: authentication, RBAC, Reception CTR, Analyst protocols/formulas, "
        "Reviewer final reports, Admin, audit trail, retention, and document generation. "
        "Out of scope: laboratory physical methods beyond software worksheets, "
        "and external LIMS integrations not present in this repository.",
    )

    add_heading(doc, "3. System overview", level=1)
    add_para(doc, f"Organization: {ORGANIZATION}")
    add_para(doc, f"Roles discovered: {', '.join(inv.roles)}")
    add_para(doc, "Workspace pages:")
    add_bullets(
        doc,
        [
            f"{p.filename}: {p.title} — roles [{', '.join(p.roles)}] — {p.summary}"
            for p in inv.pages
        ]
        or ["(no pages found)"],
    )

    add_heading(doc, "4. User requirements", level=1)
    reqs = _req_rows(inv)
    add_table(
        doc,
        ("Req ID", "Category", "Requirement", "Source"),
        reqs,
    )

    add_heading(doc, "5. Feature inventory (derived)", level=1)
    add_bullets(doc, inv.features)

    if inv.warnings:
        add_heading(doc, "6. Generation warnings", level=1)
        add_bullets(doc, inv.warnings)

    add_signature_block(doc)
    path = out_dir / dated_filename("SLS_URS", stamp)
    return save_document(doc, path)
