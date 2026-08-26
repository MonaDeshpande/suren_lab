"""Unit tests for ULR number generation."""

from __future__ import annotations

from services.ulr import (
    ULR_TOTAL_LENGTH,
    generate_ulr_no,
    lab_code_for_ulr,
    parse_ulr_parts,
)


class TestParseUlrParts:
    def test_sls_306_01(self):
        assert parse_ulr_parts("SLS/26/306/01") == ("26", "30601")

    def test_sls_306_01_02(self):
        assert parse_ulr_parts("SLS/26/306/01/02") == ("26", "30601")

    def test_glg_555(self):
        assert parse_ulr_parts("GLG/26/555/01") == ("26", "55501")

    def test_fallback_year(self):
        assert parse_ulr_parts("SLS/XX/306/01", fallback_year=2027) == ("27", "30601")

    def test_too_few_segments(self):
        assert parse_ulr_parts("SLS/26/306") is None


class TestGenerateUlrNo:
    def test_total_length(self):
        ulr = generate_ulr_no("SLS/26/306/01")
        assert len(ulr) == ULR_TOTAL_LENGTH

    def test_sls_306_01(self):
        assert generate_ulr_no("SLS/26/306/01") == "TC1611826000030601F"

    def test_sls_306_01_02(self):
        assert generate_ulr_no("SLS/26/306/01/02") == "TC1611826000030601F"

    def test_sls_638_01(self):
        assert generate_ulr_no("SLS/26/638/01") == "TC1611826000063801F"

    def test_glg_555(self):
        assert generate_ulr_no("GLG/26/555/01") == "TC1611826000055501F"

    def test_empty_lab_code(self):
        assert generate_ulr_no("") == ""

    def test_fallback_year(self):
        assert (
            generate_ulr_no("SLS/XX/306/01", fallback_year=2027)
            == "TC1611827000030601F"
        )


class TestLabCodeForUlr:
    def test_prefers_lab_code(self):
        assert lab_code_for_ulr("SLS/26/306/01", "SLS-260721-0002") == "SLS/26/306/01"

    def test_falls_back_to_sample_code(self):
        assert lab_code_for_ulr("SLS-260721-0002", "SLS/26/638/01") == "SLS/26/638/01"
