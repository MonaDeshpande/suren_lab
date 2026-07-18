"""
Unit tests for CTR validate_request and catalog input helpers (TC-REC / TC-FOR).
"""

from __future__ import annotations

from datetime import date

from services.customers import Customer
from services.protocols.test_catalog import get_test, missing_required_inputs
from services.requests import SampleRow, TestRequestData, validate_request


def _customer(**overrides) -> Customer:
    base = dict(
        customer_name="ABC Foods",
        address="1 Lab Road",
        contact_person="Ravi",
        contact_number="9876543210",
        email="ravi@example.com",
        gst_number="27AAAAA0000A1Z5",
    )
    base.update(overrides)
    return Customer(**base)


def _valid_request(**overrides) -> TestRequestData:
    data = TestRequestData(
        customer=_customer(),
        request_date=date(2026, 7, 17),
        samples=[
            SampleRow(
                sr_no=1,
                sample_name="Jaggery",
                test_keys=["moisture"],
            )
        ],
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


class TestValidateRequest:
    def test_valid_ok(self):
        assert validate_request(_valid_request()) == []

    def test_missing_customer_name(self):
        data = _valid_request()
        data.customer.customer_name = "  "
        errors = validate_request(data)
        assert any("name" in e.lower() for e in errors)

    def test_missing_gst(self):
        data = _valid_request()
        data.customer.gst_number = ""
        errors = validate_request(data)
        assert any("GST" in e for e in errors)

    def test_missing_contact_person(self):
        data = _valid_request()
        data.customer.contact_person = ""
        assert any("contact person" in e.lower() for e in validate_request(data))

    def test_missing_contact_number(self):
        data = _valid_request()
        data.customer.contact_number = ""
        assert any("Contact number" in e for e in validate_request(data))

    def test_missing_email(self):
        data = _valid_request()
        data.customer.email = ""
        assert any("Email" in e for e in validate_request(data))

    def test_missing_date(self):
        data = _valid_request(request_date=None)
        assert any("Date" in e for e in validate_request(data))

    def test_no_samples(self):
        data = _valid_request(samples=[SampleRow(sr_no=1)])
        assert any("at least one sample" in e.lower() for e in validate_request(data))

    def test_sample_name_required(self):
        data = _valid_request(
            samples=[
                SampleRow(sr_no=1, sample_name="", test_keys=["moisture"], batch_code="B1")
            ]
        )
        # Row is not empty (batch_code + keys) but name missing
        errors = validate_request(data)
        assert any("name of sample" in e.lower() for e in errors)

    def test_tests_or_parameters_required(self):
        data = _valid_request(
            samples=[SampleRow(sr_no=1, sample_name="Jaggery", test_keys=[], parameters="")]
        )
        errors = validate_request(data)
        assert any("catalog test" in e.lower() for e in errors)

    def test_water_category_no_tests_yet(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Borewell",
                    category="water",
                    test_keys=["moisture"],
                    parameters="",
                )
            ]
        )
        errors = validate_request(data)
        assert any("no catalog tests" in e.lower() for e in errors)

    def test_parameters_alone_ok(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    test_keys=[],
                    parameters="Moisture",
                )
            ]
        )
        assert validate_request(data) == []

    def test_empty_trailing_row_ignored(self):
        data = _valid_request(
            samples=[
                SampleRow(sr_no=1, sample_name="Jaggery", test_keys=["moisture"]),
                SampleRow(sr_no=2),
            ]
        )
        assert validate_request(data) == []

    def test_address_not_required_by_validator(self):
        """Known gap: UI may mark address required; service does not."""
        data = _valid_request()
        data.customer.address = ""
        assert validate_request(data) == []


class TestMissingRequiredInputs:
    def test_optional_fields_not_listed(self):
        missing = missing_required_inputs(
            get_test("moisture"),
            {"w1": 1, "w": 1, "w2": 1, "empty_dish": ""},
        )
        assert missing == []

    def test_sucrose_no_required_inputs(self):
        assert missing_required_inputs(get_test("sucrose"), {}) == []
