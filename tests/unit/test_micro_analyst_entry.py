"""Unit tests for Micro analyst result value + unit entry."""

from __future__ import annotations

from services.micro_report_catalog import MICRO_REPORT_SPECS
from services.protocols.test_catalog import MICRO_TEST_KEYS, get_test, missing_required_inputs


class TestMicroAnalystEntry:
    def test_micro_tests_use_result_value_input(self):
        for key in MICRO_TEST_KEYS:
            test = get_test(key)
            keys = {f.key for f in test.inputs}
            assert "result_value" in keys
            assert "result_obs" not in keys

    def test_calculator_accepts_result_value(self):
        test = get_test("e_coli")
        display, numeric = test.calculate(
            {"result_value": "Absent", "result_unit": "cfu/25g"},
            {},
        )
        assert display == "Absent"
        assert numeric is None

    def test_missing_result_value_rejected(self):
        test = get_test("salmonella")
        missing = missing_required_inputs(test, {"result_unit": "cfu/25g"})
        assert "Result" in missing

    def test_fixed_unit_keys_in_builtin_specs(self):
        assert MICRO_REPORT_SPECS["total_plate_count"].limits
        assert MICRO_REPORT_SPECS["t_coliform"].limits == "Shall be Absent"
