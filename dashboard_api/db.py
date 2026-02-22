"""
db.py – Lightweight DB helper for the Dashboard API.

Reads DATABASE_URL from the environment (same variable used by the ingest
pipeline).  Call get_conn() to get a short-lived connection; always close it.
"""
from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import RealDictCursor


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it to .env at the repo root."
        )
    return url


def get_conn():
    """Return a new psycopg2 connection (caller must close)."""
    return psycopg2.connect(get_database_url())


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT and return rows as a list of dicts."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def scalar(sql: str, params: tuple = (), default=None):
    """Execute a query and return the first column of the first row."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else default
    finally:
        conn.close()
