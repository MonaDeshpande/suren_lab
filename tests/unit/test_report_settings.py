"""Unit tests for lab report settings (signatories, disclaimer)."""

from __future__ import annotations

import json

from services.report_settings import (
    ReportSettings,
    default_authorized_signatory,
    default_checked_by,
    load_report_settings,
    save_report_settings,
)
from services.test_report_pdf import DISCLAIMER_BULLETS


def test_default_signatories():
    settings = load_report_settings()
    assert default_authorized_signatory(settings) == "Dr. Surendra Nashikkar"
    assert default_checked_by(settings) == "Amruta Kulkarni"


def test_save_and_load_report_settings(tmp_path, monkeypatch):
    path = tmp_path / "report_settings.json"
    monkeypatch.setattr("services.report_settings.SETTINGS_PATH", path)
    save_report_settings(
        ReportSettings(
            signatories=[{"name": "Test User", "role": "Director"}],
            disclaimer_bullets=["Line one.", "Line two."],
            default_remark_text="Remark text.",
        )
    )
    loaded = load_report_settings()
    assert loaded.signatories[0]["name"] == "Test User"
    assert loaded.disclaimer_bullets == ["Line one.", "Line two."]
    assert loaded.default_remark_text == "Remark text."
    assert len(json.loads(path.read_text(encoding="utf-8"))["disclaimer_bullets"]) == 2
    assert len(DISCLAIMER_BULLETS) == 6
