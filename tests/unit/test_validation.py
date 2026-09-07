"""
Unit tests for CTR validate_request and catalog input helpers (TC-REC / TC-FOR).
"""

from __future__ import annotations

from datetime import date

from services.customers import Customer, ContactPerson, format_contacts_for_display
from services.protocols.test_catalog import get_test, missing_required_inputs
from services.requests import SampleRow, TestRequestData, validate_request, validation_warnings
from tests.conftest import sample_verification_kwargs

_VALID_ANALYST_ID = 1
_VALID_PROTOCOL_NO = "P-2026-001"


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


def _food_sample(**overrides) -> SampleRow:
    base = dict(
        sr_no=1,
        sample_name="Jaggery",
        parameters="FSSAI",
        parameters_select="FSSAI",
        test_keys=["moisture"],
        tests_with_logo=["moisture"],
        assigned_analyst_id=_VALID_ANALYST_ID,
        protocol_no="P-001",
        report_format="with_logo",
        package_type="fssai",
    )
    base.update(sample_verification_kwargs())
    base.update(overrides)
    return SampleRow(**base)


def _valid_request(**overrides) -> TestRequestData:
    data = TestRequestData(
        customer=_customer(),
        request_date=date(2026, 7, 17),
        lab_code="SLS/26/306",
        samples=[_food_sample()],
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


class TestValidateRequest:
    def test_valid_ok(self):
        assert validate_request(_valid_request()) == []

    def test_derives_sample_code_from_lab_code(self):
        data = _valid_request()
        validate_request(data)
        assert data.samples[0].sample_code == "SLS/26/306/01"

    def test_missing_customer_name(self):
        data = _valid_request()
        data.customer.customer_name = "  "
        errors = validate_request(data)
        assert any("name" in e.lower() for e in errors)

    def test_empty_gst_ok(self):
        data = _valid_request()
        data.customer.gst_number = ""
        assert validate_request(data) == []

    def test_partial_gst_rejected(self):
        data = _valid_request()
        data.customer.gst_number = "27AAAAA"
        errors = validate_request(data)
        assert any("15 alphanumeric" in e for e in errors)

    def test_missing_contact_person(self):
        data = _valid_request()
        data.customer.contact_person = ""
        assert any("contact person" in e.lower() for e in validate_request(data))

    def test_missing_contact_number(self):
        data = _valid_request()
        data.customer.contact_number = ""
        assert any("Contact number" in e for e in validate_request(data))

    def test_empty_email_ok(self):
        data = _valid_request()
        data.customer.email = ""
        assert validate_request(data) == []

    def test_missing_date(self):
        data = _valid_request(request_date=None)
        assert any("Date" in e for e in validate_request(data))

    def test_missing_lab_code(self):
        data = _valid_request(lab_code="")
        assert any("Lab code" in e for e in validate_request(data))

    def test_missing_verification_review_date(self):
        data = _valid_request(samples=[_food_sample(verify_review_date=None)])
        errors = validate_request(data)
        assert any("verification review date" in e.lower() for e in errors)

    def test_missing_verification_yes_no(self):
        data = _valid_request(samples=[_food_sample(verify_qty_checked=None)])
        errors = validate_request(data)
        assert any("Sample Quantity" in e for e in errors)

    def test_missing_analyst_assignment(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    test_keys=["moisture"],
                )
            ]
        )
        errors = validate_request(data)
        assert any("assign a chemical analyst" in e.lower() for e in errors)

    def test_missing_protocol_number(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    parameters="FSSAI",
                    test_keys=["moisture"],
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    package_type="fssai",
                )
            ]
        )
        errors = validate_request(data)
        assert any("protocol number" in e.lower() for e in errors)

    def test_batch_only_row_treated_as_empty(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    batch_code="05",
                )
            ]
        )
        assert any("at least one sample" in e.lower() for e in validate_request(data))

    def test_sample_name_required(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="",
                    quantity="500 g",
                    test_keys=["moisture"],
                    tests_with_logo=["moisture"],
                    batch_code="B1",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                    package_type="fssai",
                )
            ]
        )
        errors = validate_request(data)
        assert any("name of sample" in e.lower() for e in errors)

    def test_tests_or_parameters_required(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    test_keys=[],
                    tests_with_logo=[],
                    parameters="",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                )
            ]
        )
        errors = validate_request(data)
        assert any("parameters" in e.lower() for e in errors)

    def test_missing_package_blocks_save(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="MissingPackage",
                    parameters="FSSAI",
                    package_type="fssai",
                    test_keys=[],
                    assigned_analyst_id=_VALID_ANALYST_ID,
                )
            ]
        )
        errors = validate_request(data)
        assert any("no active test package" in e.lower() for e in errors)

    def test_water_category_with_bundle_ok(self):
        from services.protocols.test_catalog import (
            WATER_MICRO_TEST_KEYS,
            WATER_TEST_KEYS,
            default_test_keys_for_category,
        )

        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Borewell",
                    category="water",
                    test_keys=list(default_test_keys_for_category("water")),
                    parameters="",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    assigned_micro_analyst_id=2,
                    protocol_no="P-001",
                    **sample_verification_kwargs(),
                )
            ]
        )
        assert validate_request(data) == []
        assert WATER_TEST_KEYS + WATER_MICRO_TEST_KEYS == list(
            default_test_keys_for_category("water")
        )

    def test_water_missing_micro_analyst(self):
        from services.protocols.test_catalog import default_test_keys_for_category

        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Borewell",
                    category="water",
                    test_keys=list(default_test_keys_for_category("water")),
                    parameters="",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                )
            ]
        )
        errors = validate_request(data)
        assert any("micro analyst" in e.lower() for e in errors)

    def test_water_same_chemical_and_micro_analyst_rejected(self):
        from services.protocols.test_catalog import default_test_keys_for_category

        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Borewell",
                    category="water",
                    test_keys=list(default_test_keys_for_category("water")),
                    parameters="",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    assigned_micro_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                )
            ]
        )
        errors = validate_request(data)
        assert any("different users" in e.lower() for e in errors)

    def test_water_category_invalid_food_key(self):
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
        assert any("catalog test" in e.lower() for e in errors)

    def test_micro_category_with_bundle_ok(self):
        from services.protocols.test_catalog import MICRO_TEST_KEYS

        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Paneer Gravy",
                    category="micro",
                    test_keys=list(MICRO_TEST_KEYS),
                    parameters="",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                    **sample_verification_kwargs(),
                )
            ]
        )
        assert validate_request(data) == []

    def test_parameters_alone_not_sufficient_for_food(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Jaggery",
                    parameters="FSSAI",
                    test_keys=[],
                    tests_with_logo=[],
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                    package_type="fssai",
                )
            ]
        )
        errors = validate_request(data)
        assert any("with-logo test" in e.lower() for e in errors)

    def test_empty_trailing_row_ignored(self):
        data = _valid_request(
            samples=[
                _food_sample(),
                SampleRow(sr_no=2),
            ]
        )
        assert validate_request(data) == []

    def test_is_empty_ignores_auto_assigned_tests(self):
        row = SampleRow(
            sr_no=2,
            test_keys=["moisture"],
            parameters="Moisture",
        )
        assert row.is_empty()

    def test_catalog_keys_alone_do_not_count_as_filled_row(self):
        data = _valid_request(
            samples=[
                _food_sample(sample_code="SLS-260717-0103"),
                SampleRow(
                    sr_no=2,
                    test_keys=["moisture"],
                    parameters="Moisture",
                ),
            ]
        )
        assert validate_request(data) == []

    def test_address_not_required_by_validator(self):
        """Known gap: UI may mark address required; service does not."""
        data = _valid_request()
        data.customer.address = ""
        assert validate_request(data) == []

    def test_mixed_food_families_warning(self):
        data = _valid_request(
            samples=[
                SampleRow(
                    sr_no=1,
                    sample_name="Mixed",
                    parameters="FSSAI",
                    test_keys=["moisture", "bn_protein"],
                    tests_with_logo=["moisture", "bn_protein"],
                    sample_code="SLS-260717-0104",
                    assigned_analyst_id=_VALID_ANALYST_ID,
                    protocol_no="P-001",
                    package_type="fssai",
                    **sample_verification_kwargs(),
                )
            ]
        )
        assert validate_request(data) == []
        warnings = validation_warnings(data)
        assert len(warnings) == 1
        assert "protocol templates" in warnings[0].lower()

    def test_contact_two_email_optional_when_named(self):
        data = _valid_request()
        data.customer.contacts = [
            ContactPerson(position=1, contact_name="Ravi", email="ravi@example.com"),
            ContactPerson(position=2, contact_name="Priya", email=""),
        ]
        assert validate_request(data) == []

    def test_other_parameters_requires_custom_text(self):
        data = _valid_request(
            samples=[
                _food_sample(
                    parameters="",
                    parameters_select="Other",
                    package_type="fssai",
                )
            ]
        )
        errors = validate_request(data)
        assert any("custom Parameters text" in e for e in errors)

    def test_other_parameters_custom_text_ok(self):
        data = _valid_request(
            samples=[
                _food_sample(
                    parameters="Organic certification scope",
                    parameters_select="Other",
                    package_type="fssai",
                )
            ]
        )
        assert validate_request(data) == []

    def test_ctr_parameters_display_custom_text(self):
        from services.requests import ctr_parameters_display

        sample = _food_sample(parameters="Organic certification scope")
        assert ctr_parameters_display(sample) == "Organic certification scope"

    def test_duplicate_sample_codes_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "services.requests.assign_derived_sample_codes",
            lambda data, existing=None: None,
        )
        data = _valid_request(
            samples=[
                _food_sample(
                    sr_no=1,
                    sample_name="A",
                    sample_code="SLS-260721-0099",
                ),
                _food_sample(
                    sr_no=2,
                    sample_name="B",
                    sample_code="SLS-260721-0099",
                ),
            ]
        )
        errors = validate_request(data)
        assert any("duplicate sample code" in e.lower() for e in errors)

    def test_invalid_sample_code_format(self, monkeypatch):
        monkeypatch.setattr(
            "services.requests.assign_derived_sample_codes",
            lambda data, existing=None: None,
        )
        data = _valid_request(
            samples=[
                _food_sample(
                    sample_name="A",
                    sample_code="bad code!",
                )
            ]
        )
        errors = validate_request(data)
        assert any("invalid" in e.lower() for e in errors)


class TestMissingRequiredInputs:
    def test_optional_fields_not_listed(self):
        missing = missing_required_inputs(
            get_test("moisture"),
            {"w1": 1, "w": 1, "w2": 1, "empty_dish": ""},
        )
        assert missing == []

    def test_sucrose_no_required_inputs(self):
        assert missing_required_inputs(get_test("sucrose"), {}) == []
