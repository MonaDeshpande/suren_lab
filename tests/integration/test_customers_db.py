"""
Integration tests for customer upsert (GST partial unique index).

Run: pytest -m integration tests/integration/test_customers_db.py
"""

from __future__ import annotations

import uuid

import pytest

from db.connection import get_db
from services.customers import ContactPerson, Customer, get_customer_by_gst, upsert_customer

pytestmark = pytest.mark.integration


@pytest.fixture
def clean_upsert_gst():
    gst = f"99{uuid.uuid4().hex[:10].upper()}1Z5"
    assert len(gst) == 15
    yield gst
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM customer_contacts WHERE customer_id IN "
                "(SELECT id FROM customers WHERE gst_number = %s)",
                (gst,),
            )
            cur.execute("DELETE FROM customers WHERE gst_number = %s", (gst,))


def _customer(gst: str, *, name: str = "Upsert QA Co") -> Customer:
    return Customer(
        customer_name=name,
        address="1 Test Lane",
        contact_person="QA User",
        contact_number="9876543210",
        email="qa@example.com",
        gst_number=gst,
        contacts=[
            ContactPerson(contact_name="QA User", email="qa@example.com", position=1)
        ],
    )


class TestCustomerUpsert:
    def test_upsert_twice_by_gst_updates_without_conflict_error(self, clean_upsert_gst):
        gst = clean_upsert_gst
        first = upsert_customer(_customer(gst))
        assert first.id is not None
        assert first.customer_name == "Upsert QA Co"

        second = upsert_customer(
            _customer(gst, name="Upsert QA Co Updated"),
            edit_reason="Integration test update",
        )
        assert second.id == first.id
        assert second.customer_name == "Upsert QA Co Updated"

        loaded = get_customer_by_gst(gst)
        assert loaded is not None
        assert loaded.id == first.id
        assert loaded.customer_name == "Upsert QA Co Updated"
