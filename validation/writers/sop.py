"""Generate Standard Operating Procedures (SOP) Word draft."""

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


def write_sop(inv: SystemInventory, out_dir: Path, stamp: str) -> Path:
    doc = new_document()
    add_cover(
        doc,
        doc_title="Standard Operating Procedures — System Operation",
        doc_code="SLS-SOP-SYS",
        generated_at=inv.generated_at,
        subtitle="DRAFT – for review and sign-off (role-based system SOPs)",
    )

    add_heading(doc, "1. Purpose", level=1)
    add_para(
        doc,
        f"Describe how authorized staff operate the {SYSTEM_NAME} "
        "for intake, analysis, reporting, administration, and retention cleanup.",
    )

    add_heading(doc, "2. Scope", level=1)
    add_para(
        doc,
        "Applies to all users of the Streamlit application. Does not replace "
        "laboratory analytical method SOPs for physical testing.",
    )

    add_heading(doc, "3. Responsibilities", level=1)
    add_table(
        doc,
        ("Role", "Responsibilities"),
        [
            ("admin", "User accounts, roles, password reset, audit review, full workspace access"),
            ("reception", "Customer Test Request intake, sample codes, CTR documents"),
            ("analyst", "Protocol worksheets, calculations, protocol documents, status updates"),
            ("reviewer", "Review data, Final Test Report PDF, status reported"),
        ],
    )
    add_para(doc, f"Roles discovered in code: {', '.join(inv.roles)}")

    add_heading(doc, "4. System access (all users)", level=1)
    add_heading(doc, "4.1 Login", level=2)
    add_bullets(
        doc,
        [
            "Open the application (run_app.bat or http://localhost:8501).",
            "Enter username and password provided by Admin.",
            "On first login with a temporary password, complete forced password change "
            "(new password ≥ 6 characters) before using workspaces.",
            "Use Log out in the sidebar when finished.",
        ],
    )
    add_heading(doc, "4.2 Workspace pages", level=2)
    add_bullets(
        doc,
        [
            f"{p.filename}: {p.title} — allowed roles: {', '.join(p.roles)}. {p.summary}"
            for p in inv.pages
        ]
        or ["(no pages inventoried)"],
    )

    add_heading(doc, "5. SOP — Reception (CTR)", level=1)
    add_para(doc, "Related code: pages/1_Reception.py, services/requests.py, customers.py, samples.py")
    add_heading(doc, "5.1 Procedure", level=2)
    add_bullets(
        doc,
        [
            "Sign in with reception (or admin) role; open Reception workspace.",
            "Enter / confirm customer details (GST is the unique customer key).",
            "Complete CTR fields (date, lab code, service type, delivery, samples, tests).",
            "Save the request; note generated sample codes (SLS-YYMMDD-NNNN).",
            "Download CTR PDF and/or Word as required by lab practice.",
            "Hand off sample codes to Analyst.",
        ],
    )
    add_heading(doc, "5.2 Records", level=2)
    add_bullets(
        doc,
        [
            "CTR PDF/DOCX with generator stamp",
            "Audit: customer.upsert, request.save, report.ctr",
        ],
    )

    add_heading(doc, "6. SOP — Analyst (protocol)", level=1)
    add_para(doc, "Related code: pages/2_Analyst.py, protocol_store.py, test_catalog.py")
    add_heading(doc, "6.1 Procedure", level=2)
    add_bullets(
        doc,
        [
            "Sign in with analyst (or admin) role; open Analyst workspace.",
            "Search / select sample by sample_code.",
            "Complete protocol header fields.",
            "Enter worksheet inputs for each selected catalog test; verify calculated results.",
            "Save results; update status to completed when work is finished.",
            "Generate protocol PDF/DOCX if required.",
        ],
    )
    add_heading(doc, "6.2 Shared catalog tests", level=2)
    if inv.lab_tests:
        add_table(
            doc,
            ("Key", "Name", "Method", "Unit", "Formula"),
            [
                (t.key, t.name, t.method, t.unit, t.formula_display)
                for t in inv.lab_tests
            ],
        )
    else:
        add_para(doc, "No catalog tests found.")
    add_heading(doc, "6.3 Records", level=2)
    add_bullets(
        doc,
        [
            "Protocol PDF/DOCX with generator stamp",
            "Audit: protocol.upsert, result.save, sample.status, report.protocol",
        ],
    )

    add_heading(doc, "7. SOP — Reviewer (final report)", level=1)
    add_para(doc, "Related code: pages/3_Reviewer.py, test_report_pdf.py")
    add_heading(doc, "7.1 Procedure", level=2)
    add_bullets(
        doc,
        [
            "Sign in with reviewer (or admin) role; open Reviewer workspace.",
            "Select sample; review reception CTR data and analyst results.",
            "Confirm preconditions for final report are met.",
            "Generate Final Test Report PDF (QSF 7.8.2); status becomes reported.",
            "Apply wet-ink signature on printed report per lab QMS if required.",
        ],
    )
    add_heading(doc, "7.2 Records", level=2)
    add_bullets(doc, ["Final Test Report PDF", "Audit: report.final"])

    add_heading(doc, "8. SOP — Admin (users & audit)", level=1)
    add_para(doc, "Related code: pages/4_Admin.py, services/users.py, audit.py")
    add_heading(doc, "8.1 Procedure", level=2)
    add_bullets(
        doc,
        [
            "Sign in as admin; open Admin workspace.",
            "Create users with temporary password; assign role "
            f"({', '.join(inv.roles)}).",
            "Change roles, activate/deactivate accounts, or reset passwords as needed.",
            "Do not deactivate the last active admin (system protects this).",
            "Review audit log periodically for unusual activity.",
        ],
    )
    add_heading(doc, "8.2 Audit actions monitored", level=2)
    add_bullets(doc, inv.audit_actions or ["(none discovered)"])

    add_heading(doc, "9. SOP — Sample retention & cleanup", level=1)
    add_bullets(
        doc,
        [
            "Sample rows expire after 50 days (expires_at).",
            "Cleanup may run automatically when the app opens, and/or manually via "
            "python scripts/cleanup_expired_samples.py.",
            "Customer master records are permanent and must not be deleted by retention purge.",
            "Record evidence of purge when performed as a controlled activity "
            "(audit: sample.purge_expired).",
        ],
    )

    add_heading(doc, "10. Service modules reference", level=1)
    add_table(
        doc,
        ("Module", "Path", "Summary"),
        [
            (s.name, s.path, (s.docstring or "")[:120])
            for s in inv.services[:40]
        ],
    )

    add_heading(doc, "11. Database entities", level=1)
    add_table(
        doc,
        ("Table", "Key columns", "Notes"),
        [
            (
                t.name,
                ", ".join(t.columns[:8]) + ("…" if len(t.columns) > 8 else ""),
                t.comment[:100],
            )
            for t in inv.tables
        ],
    )

    add_signature_block(doc)
    path = out_dir / dated_filename("SLS_SOP_System_Operation", stamp)
    return save_document(doc, path)
