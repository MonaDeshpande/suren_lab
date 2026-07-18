"""
services/customers.py
---------------------
Permanent customer master — lookup and upsert by GST number.

These fields are stored forever and reused on later test requests:
  customer_name, address, contact_person, contact_number, email, gst_number
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user


@dataclass
class Customer:
    """
    In-memory representation of one row in the `customers` table.

    Attributes
    ----------
    id : optional DB primary key (None for a brand-new customer not yet saved)
    customer_name : company / customer name shown on the form
    address : full address
    contact_person : name of the contact person
    contact_number : phone / mobile
    email : email id
    gst_number : GSTIN — unique business key
    """

    customer_name: str
    address: str
    contact_person: str
    contact_number: str
    email: str
    gst_number: str
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict (useful for Streamlit session / debugging)."""
        return asdict(self)


def search_customers(query: str, limit: int = 20) -> list[Customer]:
    """
    Search permanent customers by GST number or name (case-insensitive).

    Parameters
    ----------
    query : partial GST or customer name typed by the user
    limit : max rows to return

    Returns
    -------
    list[Customer]
    """
    q = (query or "").strip()
    if not q:
        return list_recent_customers(limit=limit)

    sql = """
        SELECT id, customer_name, address, contact_person,
               contact_number, email, gst_number
          FROM customers
         WHERE gst_number ILIKE %s
            OR customer_name ILIKE %s
         ORDER BY customer_name
         LIMIT %s
    """
    pattern = f"%{q}%"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pattern, pattern, limit))
            rows = cur.fetchall()

    return [_row_to_customer(r) for r in rows]


def list_recent_customers(limit: int = 20) -> list[Customer]:
    """Return the most recently updated customers (for the picker default list)."""
    sql = """
        SELECT id, customer_name, address, contact_person,
               contact_number, email, gst_number
          FROM customers
         ORDER BY updated_at DESC
         LIMIT %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()

    return [_row_to_customer(r) for r in rows]


def get_customer_by_id(customer_id: int) -> Optional[Customer]:
    """Fetch a single customer by primary key, or None if missing."""
    sql = """
        SELECT id, customer_name, address, contact_person,
               contact_number, email, gst_number
          FROM customers
         WHERE id = %s
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (customer_id,))
            row = cur.fetchone()

    return _row_to_customer(row) if row else None


def get_customer_by_gst(gst_number: str) -> Optional[Customer]:
    """Fetch a single customer by GST number (exact match, case-insensitive)."""
    sql = """
        SELECT id, customer_name, address, contact_person,
               contact_number, email, gst_number
          FROM customers
         WHERE UPPER(TRIM(gst_number)) = UPPER(TRIM(%s))
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (gst_number,))
            row = cur.fetchone()

    return _row_to_customer(row) if row else None


def upsert_customer(customer: Customer, actor=None) -> Customer:
    """
    Insert a new customer, or update the existing one matched by GST number.

    This is how "permanent" storage works:
      - First visit with a GST  → INSERT
      - Later visit with same GST → UPDATE name/address/contact/email

    Returns
    -------
    Customer
        The saved record including the database `id`.
    """
    gst = (customer.gst_number or "").strip()
    if not gst:
        raise ValueError("GST number is required to save a customer permanently.")

    if not (customer.customer_name or "").strip():
        raise ValueError("Customer name / details are required.")

    # Normalise GST for consistent unique key storage
    gst = gst.upper()

    sql = """
        INSERT INTO customers (
            customer_name, address, contact_person,
            contact_number, email, gst_number
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (gst_number) DO UPDATE SET
            customer_name  = EXCLUDED.customer_name,
            address        = EXCLUDED.address,
            contact_person = EXCLUDED.contact_person,
            contact_number = EXCLUDED.contact_number,
            email          = EXCLUDED.email,
            updated_at     = NOW()
        RETURNING id, customer_name, address, contact_person,
                  contact_number, email, gst_number
    """
    values = (
        customer.customer_name.strip(),
        (customer.address or "").strip(),
        (customer.contact_person or "").strip(),
        (customer.contact_number or "").strip(),
        (customer.email or "").strip(),
        gst,
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            row = cur.fetchone()

    saved = _row_to_customer(row)
    log_from_user(
        actor,
        "customer.upsert",
        "customers",
        saved.id,
        details=f"gst={saved.gst_number}",
    )
    return saved


def _row_to_customer(row: tuple) -> Customer:
    """Map a SQL row tuple to a Customer dataclass."""
    return Customer(
        id=row[0],
        customer_name=row[1] or "",
        address=row[2] or "",
        contact_person=row[3] or "",
        contact_number=row[4] or "",
        email=row[5] or "",
        gst_number=row[6] or "",
    )
