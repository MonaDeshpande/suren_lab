"""
services/customers.py
---------------------
Permanent customer master — lookup and upsert by GST number.

These fields are stored forever and reused on later test requests:
  customer_name, address, contact_person, contact_number, email, gst_number

Up to five contact persons (name + email) are stored in customer_contacts.
The first contact is mirrored on the customers row for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Optional

from db.connection import get_db
from services.audit import log_from_user
from services.versions import customer_snapshot, save_version, validate_edit_reason

MAX_CONTACTS = 5
GSTIN_LENGTH = 15


@dataclass
class ContactPerson:
    """One contact person on a customer record (position 1–5)."""

    contact_name: str = ""
    email: str = ""
    position: int = 1


@dataclass
class Customer:
    """
    In-memory representation of one row in the `customers` table.

    Attributes
    ----------
    id : optional DB primary key (None for a brand-new customer not yet saved)
    customer_name : company / customer name shown on the form
    address : full address
    contact_person : primary contact name (contact 1)
    contact_number : primary phone / mobile
    email : primary email (contact 1)
    gst_number : GSTIN — unique business key
    contacts : up to five contact persons (name + email)
    """

    customer_name: str
    address: str
    contact_person: str
    contact_number: str
    email: str
    gst_number: str
    id: Optional[int] = None
    contacts: list[ContactPerson] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict (useful for Streamlit session / debugging)."""
        return asdict(self)

    def resolved_contacts(self) -> list[ContactPerson]:
        """Return up to five contacts, falling back to legacy single-contact fields."""
        cleaned = [
            ContactPerson(
                contact_name=(c.contact_name or "").strip(),
                email=(c.email or "").strip(),
                position=c.position or (i + 1),
            )
            for i, c in enumerate(self.contacts or [])
            if (c.contact_name or "").strip() or (c.email or "").strip()
        ]
        if cleaned:
            return cleaned[:MAX_CONTACTS]
        if (self.contact_person or "").strip() or (self.email or "").strip():
            return [
                ContactPerson(
                    contact_name=(self.contact_person or "").strip(),
                    email=(self.email or "").strip(),
                    position=1,
                )
            ]
        return [ContactPerson(position=1)]


def format_contacts_for_display(contacts: list[ContactPerson]) -> tuple[str, str]:
    """
    Format contact names and emails for CTR PDF/DOCX cells.

    Returns (names_text, emails_text).
    """
    active = [
        c
        for c in contacts
        if (c.contact_name or "").strip() or (c.email or "").strip()
    ]
    if not active:
        return "", ""

    if len(active) == 1:
        c = active[0]
        return (c.contact_name or "").strip(), (c.email or "").strip()

    names: list[str] = []
    emails: list[str] = []
    for c in active:
        pos = c.position or (len(names) + 1)
        if (c.contact_name or "").strip():
            names.append(f"{pos}. {c.contact_name.strip()}")
        if (c.email or "").strip():
            emails.append(f"{pos}. {c.email.strip()}")
    return "\n".join(names), "\n".join(emails)


def gst_ready_for_lookup(gst_number: str) -> bool:
    """True when GST looks complete enough to query the permanent customer master."""
    gst = (gst_number or "").strip().upper()
    return len(gst) == GSTIN_LENGTH and gst.isalnum()


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
         WHERE is_active = TRUE
           AND (gst_number ILIKE %s
            OR customer_name ILIKE %s)
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
         WHERE is_active = TRUE
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
         WHERE id = %s AND is_active = TRUE
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (customer_id,))
            row = cur.fetchone()

    if not row:
        return None
    customer = _row_to_customer(row)
    customer.contacts = list_contacts(customer.id)
    return customer


def get_customer_by_gst(gst_number: str) -> Optional[Customer]:
    """Fetch a single customer by GST number (exact match, case-insensitive)."""
    sql = """
        SELECT id, customer_name, address, contact_person,
               contact_number, email, gst_number
          FROM customers
         WHERE is_active = TRUE
           AND UPPER(TRIM(gst_number)) = UPPER(TRIM(%s))
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (gst_number,))
            row = cur.fetchone()

    if not row:
        return None
    customer = _row_to_customer(row)
    customer.contacts = list_contacts(customer.id)
    return customer


def list_contacts(customer_id: Optional[int]) -> list[ContactPerson]:
    """Load contact persons for a customer (empty list when id is None)."""
    if customer_id is None:
        return []
    sql = """
        SELECT position, contact_name, email
          FROM customer_contacts
         WHERE customer_id = %s AND is_active = TRUE
         ORDER BY position
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (customer_id,))
            rows = cur.fetchall()
    return [
        ContactPerson(
            position=row[0],
            contact_name=row[1] or "",
            email=row[2] or "",
        )
        for row in rows
    ]


def _contacts_equal(a: list[ContactPerson], b: list[ContactPerson]) -> bool:
    def norm(contacts: list[ContactPerson]) -> list[tuple[int, str, str]]:
        cleaned = [
            (
                c.position or (i + 1),
                (c.contact_name or "").strip(),
                (c.email or "").strip(),
            )
            for i, c in enumerate(contacts)
            if (c.contact_name or "").strip() or (c.email or "").strip()
        ]
        return sorted(cleaned, key=lambda x: x[0])

    return norm(a) == norm(b)


def customer_data_changed(existing: Customer, proposed: Customer) -> bool:
    """True when proposed customer differs from the stored record."""
    fields = (
        "customer_name",
        "address",
        "contact_person",
        "contact_number",
        "email",
    )
    for name in fields:
        if (getattr(existing, name) or "").strip() != (
            getattr(proposed, name) or ""
        ).strip():
            return True
    if (existing.gst_number or "").strip().upper() != (
        proposed.gst_number or ""
    ).strip().upper():
        return True
    return not _contacts_equal(
        existing.resolved_contacts(),
        proposed.resolved_contacts(),
    )


def replace_contacts(
    customer_id: int,
    contacts: list[ContactPerson],
    actor=None,
) -> None:
    """Replace all contact rows for a customer (max five)."""
    active = [
        ContactPerson(
            contact_name=(c.contact_name or "").strip(),
            email=(c.email or "").strip(),
            position=i + 1,
        )
        for i, c in enumerate(contacts[:MAX_CONTACTS])
        if (c.contact_name or "").strip() or (c.email or "").strip()
    ]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM customer_contacts WHERE customer_id = %s",
                (customer_id,),
            )
            for c in active:
                cur.execute(
                    """
                    INSERT INTO customer_contacts (
                        customer_id, position, contact_name, email
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        customer_id,
                        c.position,
                        c.contact_name,
                        (c.email or "").strip() or None,
                    ),
                )

    log_from_user(
        actor,
        "customer.contacts",
        "customer_contacts",
        customer_id,
        details=f"count={len(active)}",
    )


def upsert_customer(
    customer: Customer,
    *,
    edit_reason: str | None = None,
    actor=None,
) -> Customer:
    """
    Insert a new customer, or update an existing one.

    When GST is provided (15-character GSTIN), match by GST number.
    When GST is blank, update by ``customer.id`` if set, otherwise insert.

    Contact persons (up to five) are stored in customer_contacts; contact 1
    is mirrored on the customers row.

    Returns
    -------
    Customer
        The saved record including the database ``id``.
    """
    if not (customer.customer_name or "").strip():
        raise ValueError("Customer name / details are required.")

    contacts = customer.resolved_contacts()
    primary = contacts[0] if contacts else ContactPerson()
    contact_person = (primary.contact_name or customer.contact_person or "").strip()
    email = (primary.email or customer.email or "").strip()

    gst_raw = (customer.gst_number or "").strip()
    gst: str | None = gst_raw.upper() if gst_raw else None

    existing: Customer | None = None
    if gst and gst_ready_for_lookup(gst):
        existing = get_customer_by_gst(gst)
    elif customer.id is not None:
        existing = get_customer_by_id(customer.id)

    proposed = Customer(
        id=existing.id if existing else customer.id,
        customer_name=customer.customer_name.strip(),
        address=(customer.address or "").strip(),
        contact_person=contact_person,
        contact_number=(customer.contact_number or "").strip(),
        email=email,
        gst_number=gst or "",
        contacts=contacts,
    )

    is_update = existing is not None
    changed = is_update and customer_data_changed(existing, proposed)
    if changed:
        validate_edit_reason(edit_reason or "")
        save_version(
            "customers",
            existing.id,
            customer_snapshot(existing.id),
            edit_reason or "",
            actor=actor,
        )

    values = (
        proposed.customer_name,
        proposed.address,
        proposed.contact_person,
        proposed.contact_number,
        proposed.email,
        gst,
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            if gst and gst_ready_for_lookup(gst):
                cur.execute(
                    """
                    INSERT INTO customers (
                        customer_name, address, contact_person,
                        contact_number, email, gst_number
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gst_number)
                        WHERE is_active = TRUE AND gst_number IS NOT NULL
                    DO UPDATE SET
                        customer_name  = EXCLUDED.customer_name,
                        address        = EXCLUDED.address,
                        contact_person = EXCLUDED.contact_person,
                        contact_number = EXCLUDED.contact_number,
                        email          = EXCLUDED.email,
                        updated_at     = NOW()
                    RETURNING id, customer_name, address, contact_person,
                              contact_number, email, gst_number
                    """,
                    values,
                )
            elif is_update and existing is not None:
                cur.execute(
                    """
                    UPDATE customers
                       SET customer_name  = %s,
                           address        = %s,
                           contact_person = %s,
                           contact_number = %s,
                           email          = %s,
                           gst_number     = %s,
                           updated_at     = NOW()
                     WHERE id = %s AND is_active = TRUE
                    RETURNING id, customer_name, address, contact_person,
                              contact_number, email, gst_number
                    """,
                    (*values, existing.id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO customers (
                        customer_name, address, contact_person,
                        contact_number, email, gst_number
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, customer_name, address, contact_person,
                              contact_number, email, gst_number
                    """,
                    values,
                )
            row = cur.fetchone()

    saved = _row_to_customer(row)
    replace_contacts(saved.id, contacts, actor=actor)
    saved.contacts = list_contacts(saved.id)
    details = f"gst={saved.gst_number}" if saved.gst_number else f"id={saved.id}"
    if changed:
        log_from_user(
            actor,
            "customer.update",
            "customers",
            saved.id,
            details=details,
            edit_reason=edit_reason,
        )
    else:
        log_from_user(
            actor,
            "customer.upsert",
            "customers",
            saved.id,
            details=details,
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
