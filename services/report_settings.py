"""
services/report_settings.py
---------------------------
Lab-wide defaults for food final reports: signatory names and disclaimer bullets.
Editable by Admin; Reviewer may override per report at generation time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from services.test_report_pdf import DISCLAIMER_BULLETS, REMARK_TEXT

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "data" / "report_settings.json"

DEFAULT_SIGNATORIES = [
    {"name": "Dr. Surendra Nashikkar", "role": "Director"},
    {"name": "Amruta Kulkarni", "role": "Quality Manager"},
]


@dataclass
class ReportSettings:
    signatories: list[dict[str, str]] = field(
        default_factory=lambda: list(DEFAULT_SIGNATORIES)
    )
    disclaimer_bullets: list[str] = field(
        default_factory=lambda: list(DISCLAIMER_BULLETS)
    )
    default_remark_text: str = REMARK_TEXT


def _default_settings() -> ReportSettings:
    return ReportSettings()


def load_report_settings() -> ReportSettings:
    if not SETTINGS_PATH.exists():
        return _default_settings()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_settings()
    signatories = raw.get("signatories") or list(DEFAULT_SIGNATORIES)
    bullets = raw.get("disclaimer_bullets") or list(DISCLAIMER_BULLETS)
    remark = raw.get("default_remark_text") or REMARK_TEXT
    cleaned = [
        {"name": str(s.get("name", "")).strip(), "role": str(s.get("role", "")).strip()}
        for s in signatories
        if str(s.get("name", "")).strip()
    ]
    if not cleaned:
        cleaned = list(DEFAULT_SIGNATORIES)
    return ReportSettings(
        signatories=cleaned,
        disclaimer_bullets=[str(b).strip() for b in bullets if str(b).strip()],
        default_remark_text=str(remark).strip() or REMARK_TEXT,
    )


def save_report_settings(settings: ReportSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "signatories": settings.signatories,
        "disclaimer_bullets": settings.disclaimer_bullets,
        "default_remark_text": settings.default_remark_text,
    }
    SETTINGS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def signatory_names(settings: ReportSettings | None = None) -> list[str]:
    cfg = settings or load_report_settings()
    return [s["name"] for s in cfg.signatories]


def default_authorized_signatory(settings: ReportSettings | None = None) -> str:
    names = signatory_names(settings)
    return names[0] if names else ""


def default_checked_by(settings: ReportSettings | None = None) -> str:
    cfg = settings or load_report_settings()
    if len(cfg.signatories) > 1:
        return cfg.signatories[1]["name"]
    return ""
