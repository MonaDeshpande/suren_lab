"""Unit tests for water dual-analyst assignment and test scoping."""

from __future__ import annotations

from services.protocols.test_catalog import (
    WATER_MICRO_TEST_KEYS,
    WATER_TEST_KEYS,
)
from services.samples import SampleRecord, water_analyst_test_keys


def _water_sample(**overrides) -> SampleRecord:
    import json

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


class TestWaterAnalystTestKeys:
    def test_chemical_analyst_gets_chemical_only(self):
        sample = _water_sample()
        keys = water_analyst_test_keys(sample, 10)
        assert keys == WATER_TEST_KEYS

    def test_micro_analyst_gets_micro_only(self):
        sample = _water_sample()
        keys = water_analyst_test_keys(sample, 20)
        assert keys == WATER_MICRO_TEST_KEYS

    def test_admin_like_sees_all(self):
        sample = _water_sample()
        keys = water_analyst_test_keys(sample, 99, is_admin_like=True)
        assert set(keys) == set(WATER_TEST_KEYS + WATER_MICRO_TEST_KEYS)

    def test_unassigned_analyst_gets_empty(self):
        sample = _water_sample()
        assert water_analyst_test_keys(sample, 99) == []
