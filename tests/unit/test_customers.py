"""Unit tests for customer contact helpers and change detection."""

from __future__ import annotations

import pytest

from services.customers import (
    ContactPerson,
    Customer,
    customer_data_changed,
    format_contacts_for_display,
    gst_ready_for_lookup,
)
from services.versions import validate_edit_reason


class TestGstReadyForLookup:
    def test_complete_gstin(self):
        assert gst_ready_for_lookup("27AAAAA0000A1Z5") is True

    def test_incomplete_gstin(self):
        assert gst_ready_for_lookup("27AAAAA") is False

    def test_empty(self):
        assert gst_ready_for_lookup("") is False


class TestFormatContactsForDisplay:
    def test_single_contact(self):
        names, emails = format_contacts_for_display(
            [ContactPerson(contact_name="Ravi", email="ravi@example.com", position=1)]
        )
        assert names == "Ravi"
        assert emails == "ravi@example.com"

    def test_multiple_contacts_numbered(self):
        names, emails = format_contacts_for_display(
            [
                ContactPerson(contact_name="Ravi", email="ravi@example.com", position=1),
                ContactPerson(contact_name="Priya", email="priya@example.com", position=2),
            ]
        )
        assert "1. Ravi" in names
        assert "2. Priya" in names
        assert "1. ravi@example.com" in emails
        assert "2. priya@example.com" in emails


class TestCustomerDataChanged:
    def _base(self) -> Customer:
        return Customer(
            customer_name="Acme Foods",
            address="123 Street",
            contact_person="Ravi",
            contact_number="9999999999",
            email="ravi@example.com",
            gst_number="27AAAAA0000A1Z5",
            contacts=[
                ContactPerson(contact_name="Ravi", email="ravi@example.com", position=1)
            ],
        )

    def test_no_change(self):
        c = self._base()
        assert customer_data_changed(c, self._base()) is False

    def test_name_change(self):
        c = self._base()
        other = self._base()
        other.customer_name = "Acme Foods Pvt Ltd"
        assert customer_data_changed(c, other) is True

    def test_contact_change(self):
        c = self._base()
        other = self._base()
        other.contacts = [
            ContactPerson(contact_name="Priya", email="priya@example.com", position=1)
        ]
        assert customer_data_changed(c, other) is True


class TestEditReasonValidation:
    def test_reason_required_for_updates(self):
        with pytest.raises(ValueError):
            validate_edit_reason("")
