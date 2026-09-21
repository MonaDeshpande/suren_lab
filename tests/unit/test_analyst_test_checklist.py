"""Unit tests for analyst assigned-test checklist helpers."""

from __future__ import annotations

import json

from services.protocol_store import TestResultRow
from services.protocols.test_catalog import (
    WATER_MICRO_TEST_KEYS,
    WATER_TEST_KEYS,
)
from services.protocol_docx import unsaved_selected_test_names
from services.samples import (
    REPORT_FORMAT_BOTH,
    SampleRecord,
    analyst_test_checklist_rows,
    assigned_test_keys_for_sample,
    logo_test_keys,
    no_logo_test_keys,
    worksheet_result_is_saved,
    water_analyst_test_keys,
)


def _food_sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS-260721-0001",
        sr_no=1,
        sample_name="Jaggery",
        batch_code="",
        quantity="500 g",
        parameters="FSSAI",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="food",
        tests_json=json.dumps(["moisture", "total_ash"]),
    )
    base.update(overrides)
    return SampleRecord(**base)


def _food_both_sample(**overrides) -> SampleRecord:
    """Food sample with report format Both (split WL / NWL, union in tests_json)."""
    return _food_sample(
        report_format=REPORT_FORMAT_BOTH,
        tests_json=json.dumps(["moisture", "total_ash"]),
        tests_with_logo_json=json.dumps(["moisture"]),
        tests_without_logo_json=json.dumps(["total_ash"]),
        assigned_analyst_id=42,
        assigned_analyst_name="Chem Analyst",
        **overrides,
    )


def _water_sample(**overrides) -> SampleRecord:
    base = dict(
        id=1,
        request_id=1,
        sample_code="SLS-260801-0001",
        sr_no=1,
        sample_name="Potable Water",
        batch_code="",
        quantity="1 L",
        parameters="",
        tests_to_perform="",
        status="pending",
        analyst_remarks="",
        created_at=None,
        expires_at=None,
        category="water",
        tests_json=json.dumps(WATER_TEST_KEYS + WATER_MICRO_TEST_KEYS),
        assigned_analyst_id=10,
        assigned_micro_analyst_id=20,
    )
    base.update(overrides)
    return SampleRecord(**base)


class TestAssignedTestKeysForSample:
    def test_respects_tests_json_subset(self):
        sample = _food_sample()
        keys = assigned_test_keys_for_sample(sample)
        assert keys == ["moisture", "total_ash"]

    def test_water_role_keys_filter_chemical(self):
        sample = _water_sample()
        role_keys = water_analyst_test_keys(sample, 10)
        keys = assigned_test_keys_for_sample(sample, role_keys=role_keys)
        assert keys == WATER_TEST_KEYS

    def test_water_role_keys_filter_micro(self):
        sample = _water_sample()
        role_keys = water_analyst_test_keys(sample, 20)
        keys = assigned_test_keys_for_sample(sample, role_keys=role_keys)
        assert keys == WATER_MICRO_TEST_KEYS


class TestAnalystTestChecklistRows:
    def test_saved_and_pending_status(self):
        sample = _food_sample()
        results = [
            TestResultRow(
                test_key="moisture",
                test_name="Moisture",
                method="IS 123",
                unit="%",
                inputs={"w1": 1},
                result_value="10.0",
                result_numeric=10.0,
            )
        ]
        rows = analyst_test_checklist_rows(sample, results)
        assert len(rows) == 2
        assert rows[0]["Test"] == "Moisture"
        assert rows[0]["Status"] == "Saved"
        assert rows[0]["Result"] == "10.0 %"
        assert rows[1]["Status"] == "Pending"
        assert rows[1]["Result"] == "—"

    def test_pending_matches_unsaved_selected_test_names(self):
        sample = _food_sample()
        results = [
            TestResultRow(
                test_key="moisture",
                test_name="Moisture",
                method="IS 123",
                unit="%",
                inputs={},
                result_value="10.0",
                result_numeric=10.0,
            )
        ]
        rows = analyst_test_checklist_rows(sample, results)
        pending = [row["Test"] for row in rows if row["Status"] == "Pending"]
        missing = unsaved_selected_test_names(sample, results)
        assert pending
        assert any("ash" in name.lower() for name in pending)
        assert any("ash" in name.lower() for name in missing)


class TestBothReportFormatAnalystVisibility:
    def test_both_format_selected_test_keys_union(self):
        sample = _food_both_sample()
        keys = sample.selected_test_keys()
        assert "moisture" in keys
        assert "total_ash" in keys
        assert len(keys) == 2

    def test_assigned_keys_include_without_logo_for_both(self):
        sample = _food_both_sample()
        keys = assigned_test_keys_for_sample(sample)
        assert "moisture" in keys
        assert "total_ash" in keys

    def test_checklist_rows_include_without_logo_for_both(self):
        sample = _food_both_sample()
        rows = analyst_test_checklist_rows(sample, [])
        test_names = [row["Test"] for row in rows]
        assert any("ash" in name.lower() for name in test_names)
        assert any("moisture" in name.lower() for name in test_names)

    def test_logo_split_does_not_shrink_analyst_keys(self):
        sample = _food_both_sample()
        assert logo_test_keys(sample) == {"moisture"}
        assert no_logo_test_keys(sample) == {"total_ash"}
        assigned = assigned_test_keys_for_sample(sample)
        assert len(assigned) == len(logo_test_keys(sample) | no_logo_test_keys(sample))


class TestWorksheetResultIsSaved:
    def test_result_value_counts_as_saved(self):
        row = TestResultRow(
            test_key="moisture",
            test_name="Moisture",
            method="",
            unit="%",
            inputs={},
            result_value="1.0",
            result_numeric=1.0,
        )
        assert worksheet_result_is_saved(row) is True

    def test_nonempty_inputs_count_as_saved(self):
        row = TestResultRow(
            test_key="moisture",
            test_name="Moisture",
            method="",
            unit="%",
            inputs={"w1": "5"},
            result_value="",
            result_numeric=None,
        )
        assert worksheet_result_is_saved(row) is True
