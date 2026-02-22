"""
db.py – PostgreSQL ingestion for extraction.json payloads.

Inserts into documents and, when applicable, into category tables
(electricity, stationary_fuel, shipping, water) per schema/documents.sql.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json


def get_connection(database_url: str):
    """Return a psycopg2 connection. Caller must close it."""
    return psycopg2.connect(database_url)


def test_connection(database_url: str) -> tuple[bool, str | None]:
    """
    Connect to PostgreSQL and run SELECT 1. Return (True, None) on success,
    (False, error_message) on failure.
    """
    try:
        conn = get_connection(database_url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def apply_schema(database_url: str, schema_path: Path | None = None) -> tuple[bool, str | None]:
    """
    Execute the schema SQL file against the database. Creates tables and indexes.
    If schema_path is None, uses schema/documents.sql relative to the package root.
    Returns (True, None) on success, (False, error_message) on failure.
    """
    if schema_path is None:
        package_root = Path(__file__).resolve().parent.parent
        schema_path = package_root / "schema" / "documents.sql"
    if not schema_path.exists():
        return False, f"Schema file not found: {schema_path}"
    sql = schema_path.read_text(encoding="utf-8")
    try:
        conn = get_connection(database_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
        finally:
            conn.close()
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def insert_document(conn, payload: dict[str, Any]) -> int:
    """
    Insert one row into documents. Return the inserted id.

    Uses payload["doc_type"], payload["source_file"], and full payload as JSONB.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (document_type, source_filename, exported_json)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (
                payload.get("doc_type") or "unknown",
                payload.get("source_file") or "",
                Json(payload),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def insert_category(conn, document_id: int, payload: dict[str, Any]) -> None:
    """
    Insert one row into the appropriate category table based on doc_type and extraction.

    Skips category insert when extraction has "error": "json_parse_failed".
    Only inserts into electricity, stationary_fuel, water when utility_type matches.
    Inserts into shipping for delivery_receipt or when extraction has logistics fields.
    """
    extraction = payload.get("extraction") or {}
    if extraction.get("error") == "json_parse_failed":
        return

    doc_type = (payload.get("doc_type") or "").strip().lower()
    utility_type = (extraction.get("utility_type") or "").strip().lower() if isinstance(extraction.get("utility_type"), str) else ""

    with conn.cursor() as cur:
        # Utility bill → electricity | stationary_fuel | water
        if doc_type == "utility_bill":
            if utility_type == "electricity":
                cur.execute(
                    """
                    INSERT INTO electricity (document_id, kwh, unit, location, period_start, period_end)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        extraction.get("electricity_kwh"),
                        "kWh",
                        extraction.get("location"),
                        extraction.get("billing_period_start"),
                        extraction.get("billing_period_end"),
                    ),
                )
                return
            if utility_type == "gas":
                cur.execute(
                    """
                    INSERT INTO stationary_fuel (document_id, fuel_type, quantity, unit, period_start, period_end)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        "natural_gas",
                        extraction.get("natural_gas_therms"),
                        "therms",
                        extraction.get("billing_period_start"),
                        extraction.get("billing_period_end"),
                    ),
                )
                return
            if utility_type == "water":
                cur.execute(
                    """
                    INSERT INTO water (document_id, water_volume, unit, location, period_start, period_end)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        extraction.get("water_volume"),
                        extraction.get("water_unit"),
                        extraction.get("location"),
                        extraction.get("billing_period_start"),
                        extraction.get("billing_period_end"),
                    ),
                )
                return
            # "other" or unknown utility_type: no category row
            return

        # Shipping: delivery_receipt or extraction with logistics fields
        has_logistics = (
            doc_type == "delivery_receipt"
            or extraction.get("mode") is not None
            or extraction.get("weight_kg") is not None
            or extraction.get("distance_km") is not None
        )
        if has_logistics:
            weight_kg = extraction.get("weight_kg")
            distance_km = extraction.get("distance_km")
            weight_tons = (float(weight_kg) / 1000.0) if weight_kg is not None else None
            distance_miles = (
                (float(distance_km) * 0.621371) if distance_km is not None else None
            )
            cur.execute(
                """
                INSERT INTO shipping (document_id, weight_tons, distance_miles, transport_mode, period_start, period_end)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    weight_tons,
                    distance_miles,
                    extraction.get("mode"),
                    extraction.get("date"),
                    None,
                ),
            )
