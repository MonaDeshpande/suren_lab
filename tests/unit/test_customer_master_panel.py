"""Unit tests for customer master helpers (no Streamlit render)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.customers import ContactPerson, Customer
from ui.components import apply_customer_to_session, read_customer_from_session
from ui.customer_master_panel import _validate_customer_for_save


class TestReadCustomerFromSession:
    @pytest.fixture
    def session_state(self):
        state = {
            "ctr_contact_count": 2,
            "f_customer_name": "Acme Foods",
            "f_address": "123 Main St",
            "f_contact_number": "9876543210",
            "f_gst_number": "27AAAAA0000A1Z5",
            "ctr_c1_name": "Jane Doe",
            "ctr_c1_email": "jane@acme.com",
            "ctr_c2_name": "John Smith",
            "ctr_c2_email": "john@acme.com",
            "_prefill_customer_key": 42,
        }
        with patch("ui.components.st") as mock_st:
            mock_st.session_state = state
            yield state

    def test_builds_customer_from_widget_keys(self, session_state):
        customer = read_customer_from_session(contact_count=2)
        assert customer.id == 42
        assert customer.customer_name == "Acme Foods"
        assert customer.address == "123 Main St"
        assert customer.contact_number == "9876543210"
        assert customer.gst_number == "27AAAAA0000A1Z5"
        assert customer.contact_person == "Jane Doe"
        assert customer.email == "jane@acme.com"
        assert len(customer.contacts) == 2
        assert customer.contacts[0].contact_name == "Jane Doe"
        assert customer.contacts[1].contact_name == "John Smith"

    def test_apply_customer_round_trip(self, session_state):
        original = Customer(
            id=7,
            customer_name="NutriHealth",
            address="Plot 5",
            contact_person="Priya",
            contact_number="9000000001",
            email="priya@nutri.com",
            gst_number="29BBBBB1111B1Z6",
            contacts=[
                ContactPerson(position=1, contact_name="Priya", email="priya@nutri.com"),
            ],
        )
        apply_customer_to_session(original)
        restored = read_customer_from_session()
        assert restored.customer_name == "NutriHealth"
        assert restored.gst_number == "29BBBBB1111B1Z6"
        assert restored.contacts[0].contact_name == "Priya"


class TestValidateCustomerForSave:
    def _minimal_customer(self, **overrides) -> Customer:
        base = Customer(
            customer_name="Test Co",
            address="Addr",
            contact_number="9999999999",
            contact_person="Alice",
            email="alice@test.com",
            gst_number="",
            contacts=[ContactPerson(position=1, contact_name="Alice", email="alice@test.com")],
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base

    def test_valid_customer_no_errors(self):
        assert _validate_customer_for_save(self._minimal_customer()) == []

    def test_missing_name(self):
        errors = _validate_customer_for_save(
            self._minimal_customer(customer_name="  ")
        )
        assert any("name" in e.lower() for e in errors)

    def test_missing_contact_name(self):
        errors = _validate_customer_for_save(
            self._minimal_customer(
                contact_person="",
                email="",
                contacts=[ContactPerson(position=1, contact_name="", email="")],
            )
        )
        assert any("contact 1" in e.lower() for e in errors)
