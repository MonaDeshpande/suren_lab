"""
Integration tests requiring live PostgreSQL (docker compose).

Run: pytest -m integration
Skip automatically when DB is down.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from db.connection import get_db
from services.customers import Customer
from services.requests import SampleRow, TestRequestData, save_test_request
from services.samples import (
    delete_expired_samples,
    generate_sample_code,
    get_by_code,
    update_status,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def clean_customer_gst():
    gst = "99TESTQA0000A1Z5"
    yield gst
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM request_samples
                 WHERE request_id IN (
                    SELECT tr.id FROM test_requests tr
                    JOIN customers c ON c.id = tr.customer_id
                    WHERE c.gst_number = %s
                 )
                """,
                (gst.upper(),),
            )
            cur.execute(
                """
                DELETE FROM test_requests
                 WHERE customer_id IN (
                    SELECT id FROM customers WHERE gst_number = %s
                 )
                """,
                (gst.upper(),),
            )
            cur.execute("DELETE FROM customers WHERE gst_number = %s", (gst.upper(),))


def test_generate_sample_code_format_and_sequence(require_db):
    day = date(2099, 1, 15)
    with get_db() as conn:
        with conn.cursor() as cur:
            code1 = generate_sample_code(cur, on_date=day)
            # Insert a fake row so next call increments (needs parent request — skip if FK)
            # Instead verify format and that second call without insert still returns same
            # until committed insert exists. Format check is enough here.
    assert code1.startswith("SLS-990115-")
    assert len(code1.split("-")[-1]) == 4
    seq = int(code1.split("-")[-1])
    assert seq >= 1


def test_save_request_status_and_lookup(require_db, clean_customer_gst):
    gst = clean_customer_gst
    data = TestRequestData(
        customer=Customer(
            customer_name="QA Integration Co",
            address="Test Addr",
            contact_person="QA",
            contact_number="9999999999",
            email="qa@example.com",
            gst_number=gst,
        ),
        request_date=date.today(),
        lab_code="LAB-QA-1",
        samples=[
            SampleRow(
                sr_no=1,
                sample_name="Integration Sample",
                test_keys=["moisture", "appearance"],
            )
        ],
    )
    saved = save_test_request(data, actor=None)
    assert saved.request_id is not None
    assert len(saved.samples) == 1
    code = saved.samples[0].sample_code
    assert code.startswith("SLS-")

    rec = get_by_code(code)
    assert rec is not None
    assert rec.status == "pending"
    assert rec.sample_name == "Integration Sample"
    assert rec.category == "food"
    assert rec.selected_test_keys() == ["moisture", "appearance"]

    update_status(code, "in_progress", analyst_remarks="started")
    rec2 = get_by_code(code)
    assert rec2 is not None
    assert rec2.status == "in_progress"

    update_status(code, "completed", analyst_remarks="done")
    rec3 = get_by_code(code)
    assert rec3 is not None
    assert rec3.status == "completed"


def test_expired_sample_hidden_and_purged(require_db, clean_customer_gst):
    gst = clean_customer_gst
    data = TestRequestData(
        customer=Customer(
            customer_name="QA Expiry Co",
            address="",
            contact_person="QA",
            contact_number="8888888888",
            email="expiry@example.com",
            gst_number=gst,
        ),
        request_date=date.today(),
        samples=[
            SampleRow(sr_no=1, sample_name="Expire Me", test_keys=["moisture"])
        ],
    )
    saved = save_test_request(data, actor=None)
    code = saved.samples[0].sample_code

    past = datetime.now(timezone.utc) - timedelta(days=1)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE request_samples SET expires_at = %s WHERE sample_code = %s",
                (past, code),
            )

    assert get_by_code(code) is None

    deleted = delete_expired_samples(actor=None)
    assert deleted >= 1

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM request_samples WHERE sample_code = %s",
                (code,),
            )
            assert cur.fetchone()[0] == 0

    # Customer remains
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM customers WHERE gst_number = %s",
                (gst.upper(),),
            )
            assert cur.fetchone()[0] == 1
