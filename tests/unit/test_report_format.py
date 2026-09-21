"""

Unit tests for per-sample final report format (logo A / B / Both).

"""



from __future__ import annotations



import json



from services.requests import (
    SampleRow,
    TestRequestData,
    _apply_package_report_format_sets,
    validate_request,
)
from tests.conftest import sample_verification_kwargs

from services.samples import (

    REPORT_FORMAT_BOTH,

    REPORT_FORMAT_WITHOUT_LOGO,

    REPORT_FORMAT_WITH_LOGO,

    SampleRecord,

    logo_test_keys,

    no_logo_test_keys,

    normalize_report_format,

    report_format_label,

)



_VALID_ANALYST_ID = 1





def _sample_record(**overrides) -> SampleRecord:

    base = dict(

        id=1,

        request_id=1,

        sample_code="SLS-260730-0001",

        sr_no=1,

        sample_name="Jaggery",

        batch_code="",

        quantity="",

        parameters="",

        tests_to_perform="",

        status="pending",

        analyst_remarks="",

        created_at=None,

        expires_at=None,

        category="food",

        tests_json=json.dumps(["moisture", "total_ash", "bn_protein"]),

        lab_code="LAB/CTR/26/001",

        report_format=REPORT_FORMAT_WITH_LOGO,

        tests_with_logo_json=json.dumps(["moisture", "total_ash"]),

        tests_without_logo_json="",

    )

    base.update(overrides)

    return SampleRecord(**base)





def _valid_request(**overrides) -> TestRequestData:

    from datetime import date



    from services.customers import Customer



    data = TestRequestData(

        customer=Customer(

            customer_name="ABC Foods",

            address="1 Lab Road",

            contact_person="Ravi",

            contact_number="9876543210",

            email="ravi@example.com",

            gst_number="27AAAAA0000A1Z5",

        ),

        request_date=date(2026, 7, 30),

        lab_code="LAB/CTR/26/001",

        samples=[

            SampleRow(

                sr_no=1,

                sample_name="Jaggery",

                parameters="FSSAI",

                test_keys=["moisture"],

                tests_with_logo=["moisture"],

                tests_without_logo=["moisture"],

                sample_code="SLS-260730-0001",

                assigned_analyst_id=_VALID_ANALYST_ID,
                protocol_no="P-001",

                report_format=REPORT_FORMAT_WITH_LOGO,

                package_type="fssai",

                **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),

            )

        ],

    )

    for key, value in overrides.items():

        setattr(data, key, value)

    return data





class TestReportFormatHelpers:

    def test_normalize_and_label(self):

        assert normalize_report_format("with_logo") == REPORT_FORMAT_WITH_LOGO

        assert normalize_report_format("A — With Logo") == REPORT_FORMAT_WITH_LOGO

        assert report_format_label(REPORT_FORMAT_WITHOUT_LOGO) == "B — Without Logo"



    def test_with_logo_uses_stored_keys(self):

        sample = _sample_record(report_format=REPORT_FORMAT_WITH_LOGO)

        assert logo_test_keys(sample) == {"moisture", "total_ash"}

        assert no_logo_test_keys(sample) == set()



    def test_without_logo_uses_stored_keys(self):

        sample = _sample_record(

            report_format=REPORT_FORMAT_WITHOUT_LOGO,

            tests_with_logo_json="",

            tests_without_logo_json=json.dumps(["bn_protein"]),

        )

        assert logo_test_keys(sample) == set()

        assert no_logo_test_keys(sample) == {"bn_protein"}



    def test_both_uses_explicit_sets(self):

        sample = _sample_record(

            report_format=REPORT_FORMAT_BOTH,

            tests_with_logo_json=json.dumps(["moisture"]),

            tests_without_logo_json=json.dumps(["total_ash"]),

        )

        assert logo_test_keys(sample) == {"moisture"}

        assert no_logo_test_keys(sample) == {"total_ash"}


class TestApplyPackageReportFormatSets:
    def test_both_format_merges_logo_sets_for_analyst_tests_json(self):
        row = SampleRow(
            sr_no=1,
            sample_name="Jaggery",
            parameters="FSSAI",
            test_keys=["moisture", "total_ash"],
            report_format=REPORT_FORMAT_BOTH,
            assigned_analyst_id=_VALID_ANALYST_ID,
            protocol_no="P-001",
            **sample_verification_kwargs(verify_lab_code="LAB/CTR/26/001"),
        )
        keys = _apply_package_report_format_sets(
            row, ["moisture"], ["total_ash"]
        )
        assert keys == ["moisture", "total_ash"]
        assert row.tests_with_logo == ["moisture"]
        assert row.tests_without_logo == ["total_ash"]


class TestValidateReportFormat:

    def test_both_requires_package_without_logo_set(self, monkeypatch):

        from services.test_packages import ResolvedPackage



        def _fake_resolve_product(*_args, **_kwargs):

            return ResolvedPackage(

                package_id=1,

                package_version_no=1,

                package_type="fssai",

                sample_product_name="Jaggery",

                test_keys=["moisture", "total_ash"],

                test_keys_with_logo=["moisture"],

                test_keys_without_logo=["total_ash"],

                display_label="Jaggery — FSSAI — tests to be conducted",

            )



        monkeypatch.setattr(
            "services.requests.resolve_package_tests", _fake_resolve_product
        )

        data = _valid_request()

        data.samples[0].report_format = REPORT_FORMAT_BOTH

        data.samples[0].tests_with_logo = ["moisture"]

        data.samples[0].tests_without_logo = []

        errors = validate_request(data)

        assert any("without-logo test" in e for e in errors)



    def test_both_valid_when_package_has_both_sets(self, monkeypatch):

        from services.test_packages import ResolvedPackage



        def _fake_resolve_product(*_args, **_kwargs):

            return ResolvedPackage(

                package_id=1,

                package_version_no=1,

                package_type="fssai",

                sample_product_name="Jaggery",

                test_keys=["moisture", "total_ash"],

                test_keys_with_logo=["moisture"],

                test_keys_without_logo=["total_ash"],

                display_label="Jaggery — FSSAI — tests to be conducted",

            )



        monkeypatch.setattr(
            "services.requests.resolve_package_tests", _fake_resolve_product
        )

        data = _valid_request()

        data.samples[0].report_format = REPORT_FORMAT_BOTH

        data.samples[0].tests_with_logo = ["moisture"]

        data.samples[0].tests_without_logo = ["total_ash"]

        assert validate_request(data) == []

