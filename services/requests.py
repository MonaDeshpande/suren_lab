"""
services/requests.py
--------------------
Save a full Customer Test Request (header + sample rows) after the form is submitted.

Flow:
  1. Upsert permanent customer (see customers.py)
  2. Insert one test_requests row
  3. Insert request_samples rows with auto sample_code (10-day expiry)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import json

from db.connection import get_db
from services.audit import log_from_user
from services.customers import Customer, upsert_customer
from services.samples import generate_sample_code
from services.protocols.test_catalog import (
    TEST_CATALOG,
    filter_keys_for_category,
    normalize_category,
    tests_for_category,
)


@dataclass
class SampleRow:
    """One line in the 'Sample Description & tests to be performed' table."""

    sr_no: int
    sample_name: str = ""
    batch_code: str = ""
    quantity: str = ""
    parameters: str = ""  # joined display names for CTR PDF
    test_keys: list[str] = field(default_factory=list)  # shared catalog keys
    category: str = "food"  # food | water | cattle_feed_fertilizer

    # Populated after save
    sample_code: str = ""

    def is_empty(self) -> bool:
        """True when the user left this sample row blank."""
        return not any(
            [
                (self.sample_name or "").strip(),
                (self.batch_code or "").strip(),
                (self.quantity or "").strip(),
                (self.parameters or "").strip(),
                bool(self.test_keys),
            ]
        )


@dataclass
class TestRequestData:
    """
    Complete payload collected from the Streamlit form.

    Permanent customer fields live on `customer`.
    Everything else is request-specific.
    """

    customer: Customer

    request_date: Optional[date] = None
    lab_code: str = ""

    number_of_samples: Optional[int] = None
    sampling_by_lab: Optional[bool] = None  # Yes / No / unset
    storage_temperature: str = ""
    test_method_spec: str = ""
    decision_rule: Optional[bool] = None  # Yes / No / unset
    service_type: str = ""  # Urgent | Regular | ""
    delivery_mode: str = ""  # Collect | Courier | Email/Whatsapp
    payment_details: str = ""
    sample_description: str = ""

    samples: list[SampleRow] = field(default_factory=list)

    # Filled after save
    request_id: Optional[int] = None


def save_test_request(data: TestRequestData, actor=None) -> TestRequestData:
    """
    Persist customer (permanent) + request + sample rows in one transaction.

    Each non-empty sample gets:
      - unique sample_code (SLS-YYMMDD-NNNN)
      - tests_to_perform from parameters
      - status = pending
      - expires_at = NOW() + 10 days

    Returns
    -------
    TestRequestData
        Same object with `customer.id`, `request_id`, and each sample's
        `sample_code` populated.
    """
    saved_customer = upsert_customer(data.customer, actor=actor)
    data.customer = saved_customer

    if saved_customer.id is None:
        raise RuntimeError("Customer was saved but no id was returned.")

    samples_to_save = [s for s in data.samples if not s.is_empty()]
    code_date = data.request_date or date.today()

    insert_request_sql = """
        INSERT INTO test_requests (
            customer_id, request_date, lab_code, number_of_samples,
            sampling_by_lab, storage_temperature, test_method_spec,
            decision_rule, service_type, delivery_mode,
            payment_details, sample_description
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
        RETURNING id
    """
    request_values = (
        saved_customer.id,
        data.request_date,
        (data.lab_code or "").strip() or None,
        data.number_of_samples,
        data.sampling_by_lab,
        (data.storage_temperature or "").strip() or None,
        (data.test_method_spec or "").strip() or None,
        data.decision_rule,
        (data.service_type or "").strip() or None,
        (data.delivery_mode or "").strip() or None,
        (data.payment_details or "").strip() or None,
        (data.sample_description or "").strip() or None,
    )

    insert_sample_sql = """
        INSERT INTO request_samples (
            request_id, sr_no, sample_name, batch_code, quantity, parameters,
            sample_code, category, tests_to_perform, tests_json, status, expires_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, 'pending', NOW() + INTERVAL '10 days'
        )
        RETURNING sample_code
    """

    saved_samples: list[SampleRow] = []

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_request_sql, request_values)
            request_id = cur.fetchone()[0]

            for sample in samples_to_save:
                category = normalize_category(sample.category)
                # Resolve display names from catalog keys when provided
                keys = filter_keys_for_category(
                    [k for k in (sample.test_keys or []) if k in TEST_CATALOG],
                    category,
                )
                if keys:
                    names = [TEST_CATALOG[k].name for k in keys]
                    tests_display = ", ".join(names)
                    tests_json = json.dumps(keys)
                else:
                    tests_display = (sample.parameters or "").strip()
                    tests_json = None
                code = generate_sample_code(cur, on_date=code_date)
                cur.execute(
                    insert_sample_sql,
                    (
                        request_id,
                        sample.sr_no,
                        (sample.sample_name or "").strip() or None,
                        (sample.batch_code or "").strip() or None,
                        (sample.quantity or "").strip() or None,
                        tests_display or None,
                        code,
                        category,
                        tests_display or None,
                        tests_json,
                    ),
                )
                returned_code = cur.fetchone()[0]
                sample.sample_code = returned_code
                sample.category = category
                sample.parameters = tests_display
                sample.test_keys = keys
                saved_samples.append(sample)


    data.request_id = request_id
    data.samples = saved_samples
    codes = ", ".join(s.sample_code for s in saved_samples if s.sample_code)
    log_from_user(
        actor,
        "request.save",
        "test_requests",
        request_id,
        details=f"samples={len(saved_samples)}" + (f" [{codes}]" if codes else ""),
    )
    return data


def validate_request(data: TestRequestData) -> list[str]:
    """
    Lightweight validation before save / PDF generation.

    Returns
    -------
    list[str]
        Human-readable error messages (empty list means OK).
    """
    errors: list[str] = []
    c = data.customer

    if not (c.customer_name or "").strip():
        errors.append("Customer details (name) are required.")
    if not (c.gst_number or "").strip():
        errors.append("GST number is required (used as permanent customer key).")
    if not (c.contact_person or "").strip():
        errors.append("Name of contact person is required.")
    if not (c.contact_number or "").strip():
        errors.append("Contact number is required.")
    if not (c.email or "").strip():
        errors.append("Email ID is required.")
    if data.request_date is None:
        errors.append("Date is required.")

    filled = [s for s in data.samples if not s.is_empty()]
    if not filled:
        errors.append("Add at least one sample row (name + tests to perform).")
    else:
        for s in filled:
            if not (s.sample_name or "").strip():
                errors.append(f"Sample Sr. {s.sr_no}: name of sample is required.")
            category = normalize_category(s.category)
            available = tests_for_category(category)
            keys = filter_keys_for_category(list(s.test_keys or []), category)
            if not keys and not (s.parameters or "").strip():
                if not available:
                    errors.append(
                        f"Sample Sr. {s.sr_no}: no catalog tests are defined yet "
                        f"for category '{category}'. Choose Food, or wait for "
                        "Water / Cattle Feed formulas."
                    )
                else:
                    errors.append(
                        f"Sample Sr. {s.sr_no}: select at least one catalog test "
                        f"for category '{category}'."
                    )

    return errors
