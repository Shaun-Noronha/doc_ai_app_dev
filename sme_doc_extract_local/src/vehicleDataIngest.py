"""
Read CSV from samples/vehicleData.csv, aggregate fuel rows, and insert into the
schema's parsed_vehicle_fuel table (defined in schema/documents.sql).

Steps:
  1. Parse and aggregate CSV rows by (period_start, period_end, fuel_type, unit).
  2. Insert one synthetic row into documents (document_type='vehicle_fuel_csv_import')
     to satisfy the FK constraint.
  3. Insert the merged fuel rows into parsed_vehicle_fuel with the new document_id.

fuel_type and unit values from the CSV are normalised to match the CHECK constraints:
  fuel_type: 'Gasoline' -> 'gasoline', 'Diesel' -> 'diesel'
  unit: 'gallons' -> 'gallon', 'liters' -> 'liter'

Uses DATABASE_URL from environment (.env). Run from package root:
    python -m src.vehicleDataIngest
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from psycopg2.extras import Json, execute_values

from src.db import get_connection

import src.config  # noqa: F401  – loads .env so DATABASE_URL is available


# ─────────────────────────────────────────────────────────────────────────────
# CHECK-constraint normalisation helpers
# ─────────────────────────────────────────────────────────────────────────────

_FUEL_TYPE_MAP: dict[str, str] = {
    "gasoline": "gasoline",
    "diesel": "diesel",
    "petrol": "gasoline",
}

_UNIT_MAP: dict[str, str] = {
    "gallon": "gallon",
    "gallons": "gallon",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
    "l": "liter",
}


def _normalise_fuel_type(raw: str) -> str | None:
    return _FUEL_TYPE_MAP.get(raw.strip().lower())


def _normalise_unit(raw: str) -> str | None:
    return _UNIT_MAP.get(raw.strip().lower())


# ─────────────────────────────────────────────────────────────────────────────
# CSV parsing and aggregation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FuelAggKey:
    period_start: str
    period_end: str
    fuel_type: str   # already normalised
    unit: str        # already normalised


def _parse_and_merge(csv_path: Path) -> List[Tuple[str, float, str, str, str]]:
    """
    Read CSV and merge rows sharing the same (period_start, period_end, fuel_type, unit).
    Quantity is the SUM of fuel_consumed.

    Returns rows as (fuel_type, quantity, unit, period_start, period_end).
    Rows with unrecognised fuel_type or unit are skipped (logged to stdout).
    """
    merged: Dict[FuelAggKey, float] = {}

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_fuel = row.get("fuel_type", "")
            raw_unit = row.get("unit", "")
            period_start = row.get("period_start", "").strip()
            period_end = row.get("period_end", "").strip()

            fuel_type = _normalise_fuel_type(raw_fuel)
            unit = _normalise_unit(raw_unit)

            if fuel_type is None:
                print(f"  [skip] unrecognised fuel_type={raw_fuel!r}")
                continue
            if unit is None:
                print(f"  [skip] unrecognised unit={raw_unit!r}")
                continue

            try:
                qty = float(row.get("fuel_consumed", 0))
            except (ValueError, TypeError):
                continue

            key = FuelAggKey(
                period_start=period_start,
                period_end=period_end,
                fuel_type=fuel_type,
                unit=unit,
            )
            merged[key] = merged.get(key, 0.0) + qty

    return [
        (key.fuel_type, qty, key.unit, key.period_start, key.period_end)
        for key, qty in sorted(
            merged.items(),
            key=lambda x: (x[0].period_start, x[0].fuel_type, x[0].unit),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Database insertion
# ─────────────────────────────────────────────────────────────────────────────

def push_fuel_to_postgres(
    database_url: str,
    csv_path: Path,
) -> int:
    """
    Insert aggregated vehicle fuel rows from the CSV into parsed_vehicle_fuel.

    Creates one row in documents (document_type='vehicle_fuel_csv_import') to satisfy
    the FK constraint, then batch-inserts the merged rows into parsed_vehicle_fuel.

    Returns the number of merged rows inserted.
    """
    merged_rows = _parse_and_merge(csv_path)
    if not merged_rows:
        print("No valid rows to insert.")
        return 0

    conn = get_connection(database_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # Create one document entry for this CSV import run.
            cur.execute(
                """
                INSERT INTO documents (document_type, source_filename, exported_json)
                VALUES (%s, %s, %s)
                RETURNING document_id
                """,
                (
                    "vehicle_fuel_csv_import",
                    csv_path.name,
                    Json({"source_file": str(csv_path), "doc_type": "vehicle_fuel_csv_import"}),
                ),
            )
            row = cur.fetchone()
            document_id = row[0] if row else None
            if not document_id:
                raise RuntimeError("Failed to obtain document_id for CSV import.")

            # Attach document_id to each fuel row.
            rows_with_doc_id = [
                (document_id, fuel_type, qty, unit, period_start, period_end)
                for fuel_type, qty, unit, period_start, period_end in merged_rows
            ]

            execute_values(
                cur,
                """
                INSERT INTO parsed_vehicle_fuel
                    (document_id, fuel_type, quantity, unit, period_start, period_end)
                VALUES %s
                """,
                rows_with_doc_id,
                page_size=200,
            )

        conn.commit()
        return len(merged_rows)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    package_root = Path(__file__).resolve().parent.parent
    csv_path = package_root / "samples" / "vehicleData.csv"

    if not csv_path.exists():
        print(f"Error: CSV not found at {csv_path}")
        exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is not set. Set it in .env or the environment.")
        exit(1)

    count = push_fuel_to_postgres(database_url=database_url, csv_path=csv_path)
    print(f"Inserted {count} merged rows into parsed_vehicle_fuel.")
