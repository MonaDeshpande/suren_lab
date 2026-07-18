"""Generate Risk Assessment Word draft (FMEA-style)."""

from __future__ import annotations

from pathlib import Path

from validation.docx_util import (
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


def _risk_rows(inv: SystemInventory) -> list[tuple[str, ...]]:
    """
    Columns: ID, Asset/Process, Threat, Impact, L, S, Risk, Mitigation, Residual
    L/S left blank for SME; Risk = LxS guidance note.
    """
    rows: list[tuple[str, ...]] = []

    def r(
        rid: str,
        asset: str,
        threat: str,
        impact: str,
        mitigation: str,
    ) -> None:
        rows.append(
            (
                rid,
                asset,
                threat,
                impact,
                "",  # Likelihood
                "",  # Severity
                "",  # Risk score
                mitigation,
                "",  # Residual
            )
        )

    r(
        "RA-001",
        "Authentication",
        "Weak or shared passwords; credential stuffing",
        "Unauthorized access to lab data / reports",
        "bcrypt hashing; forced temp password change; inactive flag; admin-managed accounts",
    )
    r(
        "RA-002",
        "RBAC",
        "User granted wrong role or admin privilege",
        "Unauthorized CTR edits, formula changes, or user admin",
        f"Role gate require_role on pages; roles limited to {', '.join(inv.roles)}; last-admin protection",
    )
    r(
        "RA-003",
        "Customer / CTR data",
        "Incorrect GST upsert or sample data entry",
        "Wrong customer linkage; incorrect sample identity",
        "GST unique key; form validation (ui/validation.py); CTR PDF/DOCX review",
    )
    r(
        "RA-004",
        "Sample codes",
        "Duplicate or non-unique sample_code",
        "Analyst opens wrong sample; report mix-up",
        "DB UNIQUE on sample_code; sequential generator SLS-YYMMDD-NNNN",
    )
    r(
        "RA-005",
        "Lab calculations",
        "Formula bug or wrong inputs",
        "Incorrect reported results (patient/client impact via lab report)",
        f"Shared catalog ({len(inv.lab_tests)} tests); unit tests test_formulas.py; display formula on worksheet",
    )
    for i, test in enumerate(inv.lab_tests, start=1):
        r(
            f"RA-005-{i:02d}",
            f"Formula: {test.name}",
            "Calculation error or missing required input",
            f"Incorrect {test.name} result ({test.unit or 'text'})",
            f"Implemented in test_catalog key={test.key}; formula: {test.formula_display}",
        )
    r(
        "RA-006",
        "Final Test Report",
        "Report generated before protocol complete / wrong sample",
        "Invalid certificate of analysis issued",
        "Reviewer preconditions; status → reported; generator stamp; QSF 7.8.2 layout",
    )
    r(
        "RA-007",
        "Audit trail",
        "Writes without audit; audit insert failure swallowed",
        "Inability to reconstruct who changed what",
        f"log_from_user for actions: {', '.join(inv.audit_actions) or 'n/a'}; Admin audit viewer",
    )
    r(
        "RA-008",
        "Sample retention purge",
        "Premature purge or failure to purge",
        "Loss of needed sample records OR stale PII/sample clutter",
        "10-day expires_at; cleanup script + app-open purge; customers permanent",
    )
    r(
        "RA-009",
        "Admin privileged actions",
        "Malicious or mistaken deactivate / password reset",
        "Lockout of staff; account takeover via reset",
        "Admin-only page; audit of user.create/set_role/set_active/reset_password; last-admin guard",
    )
    r(
        "RA-010",
        "Database / infrastructure",
        "DB down, wrong .env, exposed Postgres credentials",
        "System unavailable; data exposure",
        f"Docker Postgres {inv.docker_image} on port {inv.docker_host_port}; .env not committed; local bind",
    )
    r(
        "RA-011",
        "Document generation",
        "Wrong stamp / template / conversion failure (docx2pdf)",
        "Misattributed or missing official documents",
        "generator_stamp_lines; python-docx + ReportLab paths; Windows Word for docx2pdf",
    )
    return rows


def write_risk(inv: SystemInventory, out_dir: Path, stamp: str) -> Path:
    doc = new_document()
    add_cover(
        doc,
        doc_title="Risk Assessment Report",
        doc_code="SLS-VAL-RA",
        generated_at=inv.generated_at,
    )

    add_heading(doc, "1. Purpose", level=1)
    add_para(
        doc,
        "Identify and evaluate risks to data integrity, confidentiality, and availability "
        f"for the {SYSTEM_NAME}. Scoring is completed by SMEs.",
    )

    add_heading(doc, "2. Scoring guidance", level=1)
    add_para(doc, "Likelihood (L): 1 = Rare … 5 = Almost certain")
    add_para(doc, "Severity (S): 1 = Negligible … 5 = Critical (wrong report / data loss)")
    add_para(doc, "Risk score = L × S. Suggested bands: 1–6 Low, 8–12 Medium, 15–25 High.")
    add_para(
        doc,
        "Residual risk is assessed after mitigations. High residual risks require "
        "additional controls or formal acceptance.",
    )

    add_heading(doc, "3. Risk register (draft)", level=1)
    add_table(
        doc,
        (
            "ID",
            "Asset / Process",
            "Threat",
            "Impact",
            "L",
            "S",
            "Score",
            "Mitigation (from code)",
            "Residual",
        ),
        _risk_rows(inv),
    )

    add_heading(doc, "4. Audit actions in scope", level=1)
    add_para(
        doc,
        "Actions discovered in code: "
        + (", ".join(inv.audit_actions) if inv.audit_actions else "(none found)"),
    )

    add_signature_block(doc)
    path = out_dir / dated_filename("SLS_Risk_Assessment", stamp)
    return save_document(doc, path)
