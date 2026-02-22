"""
Goal:
- Read CSV from samples/vehicleData.csv
- Drop driver_id (and car_id, date, distance_traveled; keep only fuel fields)
- Merge/aggregate rows that share the same (period_start, period_end, fuel_type, unit)
- Create a PostgreSQL table with: fuel_type, quantity, unit, period_start, period_end
- Insert aggregated rows into Postgres (UPSERT so re-running won't duplicate)

Uses DATABASE_URL from environment (.env). Run from package root:
    python -m src.vehicleDataIngest
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import psycopg2
from psycopg2.extras import execute_values

# Load .env so DATABASE_URL is available (same as main.py)
from src.db import get_connection

# Ensure .env is loaded when run as script
import src.config  # noqa: F401


# ======= Data model for the target table =======
@dataclass(frozen=True)
class FuelAggKey:
    period_start: str
    period_end: str
    fuel_type: str
    unit: str


def _parse_and_merge(csv_path: Path) -> List[Tuple[str, str, str, float, str]]:
    """
    Read CSV from csv_path and merge rows for the same:
      (period_start, period_end, fuel_type, unit)
    Quantity is the SUM of fuel_consumed. driver_id and other non-fuel columns are ignored.
    Returns rows as (fuel_type, quantity, unit, period_start, period_end).
    """
    merged: Dict[FuelAggKey, float] = {}

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fuel_type = row.get("fuel_type", "").strip()
            unit = row.get("unit", "").strip()
            period_start = row.get("period_start", "").strip()
            period_end = row.get("period_end", "").strip()

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

    out_rows = [
        (key.fuel_type, qty, key.unit, key.period_start, key.period_end)
        for key, qty in sorted(
            merged.items(),
            key=lambda x: (x[0].period_start, x[0].fuel_type, x[0].unit),
        )
    ]
    return out_rows


def push_fuel_to_postgres(
    database_url: str,
    csv_path: Path,
    schema: str = "public",
    table: str = "parsed_vehicle_fuel",
) -> int:
    """
    Create the table if it doesn't exist and insert merged data from the CSV.
    Uses UPSERT so re-running with the same data updates quantity (adds to existing).
    Returns the number of merged rows inserted/updated.
    """
    merged_rows = _parse_and_merge(csv_path)
    if not merged_rows:
        return 0

    conn = get_connection(database_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")

            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.{table} (
                    id BIGSERIAL PRIMARY KEY,
                    fuel_type TEXT NOT NULL CHECK (fuel_type IN ('Gasoline', 'Diesel')),
                    quantity NUMERIC(10,2) NOT NULL CHECK (quantity >= 0),
                    unit TEXT NOT NULL CHECK (unit IN ('gallons', 'liters')),
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    CONSTRAINT uq_fuel_day UNIQUE (period_start, period_end, fuel_type, unit)
                );
                """
            )

            insert_sql = f"""
                INSERT INTO {schema}.{table}
                    (fuel_type, quantity, unit, period_start, period_end)
                VALUES %s
                ON CONFLICT (period_start, period_end, fuel_type, unit)
                DO UPDATE SET
                    quantity = {schema}.{table}.quantity + EXCLUDED.quantity;
            """
            execute_values(cur, insert_sql, merged_rows, page_size=200)

        conn.commit()
        return len(merged_rows)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ======= Entry point =======
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

    count = push_fuel_to_postgres(
        database_url=database_url,
        csv_path=csv_path,
        schema="public",
        table="parsed_vehicle_fuel",
    )
    print(f"Inserted/updated {count} merged rows into PostgreSQL.")
