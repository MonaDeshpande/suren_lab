"""
db/connection.py
-----------------
PostgreSQL connection helpers for the SLS Lab application.

Responsibilities:
  - Load credentials from .env
  - Open / close connections safely
  - Provide a small context-manager for queries
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection
from dotenv import load_dotenv

# Load .env from project root (safe to call multiple times)
load_dotenv()


def get_connection_params() -> dict:
    """
    Build a connection-parameter dict from environment variables.

    Returns
    -------
    dict
        Keys accepted by psycopg2.connect(...)
    """
    return {
        # Prefer 127.0.0.1 over "localhost" so Windows does not use IPv6 (::1),
        # which often hits a different (local) PostgreSQL than the Docker one.
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5433")),
        "dbname": os.getenv("POSTGRES_DB", "sls_lab"),
        "user": os.getenv("POSTGRES_USER", "sls_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "sls_secure_password"),
    }


def get_connection() -> PgConnection:
    """
    Open a new PostgreSQL connection.

    Caller is responsible for closing it (prefer `get_db()` below).
    """
    return psycopg2.connect(**get_connection_params())


@contextmanager
def get_db() -> Generator[PgConnection, None, None]:
    """
    Context manager that yields a live connection and always closes it.

    Example
    -------
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    """
    conn = get_connection()
    try:
        yield conn
        # Commit any pending work if the caller did not already
        conn.commit()
    except Exception:
        # Roll back on error so the session stays clean
        conn.rollback()
        raise
    finally:
        conn.close()


def test_connection() -> tuple[bool, str]:
    """
    Quick health-check used by the Streamlit UI.

    Returns
    -------
    (ok, message)
        ok=True and a short success message, or ok=False and the error text.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, "Connected to PostgreSQL successfully."
    except Exception as exc:  # noqa: BLE001 — surface any DB error to the UI
        return False, str(exc)
