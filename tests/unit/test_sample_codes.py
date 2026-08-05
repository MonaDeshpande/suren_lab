"""Unit tests for sample code allocation helpers."""

from __future__ import annotations

import pytest

from services.requests import SampleRow, TestRequestData, assign_derived_sample_codes
from services.samples import (
    allocate_sample_code,
    derive_sample_code,
    derive_sample_codes,
    is_valid_sample_code_format,
    normalize_lab_code,
    normalize_sample_code,
)
from services.customers import Customer


class TestSampleCodeFormat:
    def test_normalize_uppercase(self):
        assert normalize_sample_code(" sls-260721-0001 ") == "SLS-260721-0001"

    def test_valid_auto_format(self):
        assert is_valid_sample_code_format("SLS-260721-0001")

    def test_valid_custom_format(self):
        assert is_valid_sample_code_format("LAB/CTR/26/001")

    def test_valid_lab_code_derived_format(self):
        assert is_valid_sample_code_format("SLS/26/306/01")

    def test_rejects_spaces(self):
        assert not is_valid_sample_code_format("bad code")

    def test_rejects_too_short(self):
        assert not is_valid_sample_code_format("AB")


class TestDeriveSampleCode:
    def test_normalize_lab_code(self):
        assert normalize_lab_code(" sls/26/306 ") == "SLS/26/306"

    def test_single_sample_zero_padded_suffix(self):
        assert derive_sample_code("SLS/26/306", index=1, total=1) == "SLS/26/306/01"

    def test_multiple_samples_with_suffix(self):
        assert derive_sample_code("SLS/26/306", index=1, total=3) == "SLS/26/306/01"
        assert derive_sample_code("SLS/26/306", index=2, total=3) == "SLS/26/306/02"
        assert derive_sample_code("SLS/26/306", index=3, total=3) == "SLS/26/306/03"

    def test_derive_sample_codes_list(self):
        assert derive_sample_codes("SLS/26/306", 2) == [
            "SLS/26/306/01",
            "SLS/26/306/02",
        ]


class TestAssignDerivedSampleCodes:
    def _request(self, lab_code: str, samples: list[SampleRow]) -> TestRequestData:
        return TestRequestData(
            customer=Customer(
                customer_name="Test Co",
                address="Test Address",
                gst_number="27AAAAA0000A1Z5",
                contact_person="A",
                contact_number="9999999999",
                email="a@example.com",
            ),
            lab_code=lab_code,
            samples=samples,
        )

    def test_assigns_single_sample_code(self):
        data = self._request(
            "SLS/26/306",
            [SampleRow(sr_no=1, sample_name="Jaggery", test_keys=["moisture"])],
        )
        assign_derived_sample_codes(data)
        assert data.samples[0].sample_code == "SLS/26/306/01"

    def test_assigns_multi_sample_suffixes_by_sr_order(self):
        data = self._request(
            "SLS/26/306",
            [
                SampleRow(sr_no=2, sample_name="B", test_keys=["moisture"]),
                SampleRow(sr_no=1, sample_name="A", test_keys=["moisture"]),
            ],
        )
        assign_derived_sample_codes(data)
        by_sr = {s.sr_no: s.sample_code for s in data.samples}
        assert by_sr[1] == "SLS/26/306/01"
        assert by_sr[2] == "SLS/26/306/02"

    def test_locked_sample_keeps_stored_code_on_edit(self):
        data = self._request(
            "SLS/26/999",
            [
                SampleRow(
                    sr_no=1,
                    id=10,
                    sample_name="A",
                    test_keys=["moisture"],
                    sample_code="SLS/26/306",
                    status="in_progress",
                ),
            ],
        )
        existing = self._request(
            "SLS/26/306",
            [
                SampleRow(
                    sr_no=1,
                    id=10,
                    sample_name="A",
                    test_keys=["moisture"],
                    sample_code="SLS/26/306",
                    status="in_progress",
                ),
            ],
        )
        assign_derived_sample_codes(data, existing)
        assert data.samples[0].sample_code == "SLS/26/306"


class TestAllocateSampleCode:
    def test_requires_reception_code(self):
        with pytest.raises(ValueError, match="Sample code is required"):
            allocate_sample_code(None, requested="")
