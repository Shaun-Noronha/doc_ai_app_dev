"""
calculations.py – Backend emission & sustainability metric calculation engine.

Each public function reads activity data from the category tables that have
already been populated by the extraction pipeline, applies the appropriate
emission formula, and writes results to the ``activities``, ``emissions``,
``energy_metrics``, ``water_metrics``, and ``waste_metrics`` tables.

Emission formula references
────────────────────────────
 Activity                  Scope  Formula
 ─────────────────────────────────────────────────────────────────────────
 Purchased Electricity      2     kWh × grid_factor (kg CO₂e/kWh)
 Stationary Fuel Combustion 1     quantity × fuel_factor (kg CO₂e/unit)
 Vehicle Fuel Use           1     quantity × fuel_factor (kg CO₂e/unit)
 Transportation & Shipping  3     (weight_tons × distance_miles) × mode_factor
 Waste Generation           3     waste_kg × disposal_factor (kg CO₂e/kg)
 Water Usage                —     sum of water_volume (non-GHG resource metric)

Derived metrics written to dedicated tables
───────────────────────────────────────────
 Energy Intensity   = total_kWh  ÷ business_unit
 Water Intensity    = total_water ÷ business_unit
 Waste Diversion %  = (recycled + composted) ÷ total_waste

Usage
──────
    from src.db import get_connection
    from src.calculations import run_all_calculations

    conn = get_connection(DATABASE_URL)
    summary = run_all_calculations(conn, period_start="2024-01-01", period_end="2024-12-31")
    conn.close()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.emission_factors import (
    get_electricity_factor,
    get_stationary_fuel_factor,
    get_vehicle_fuel_factor,
    get_transport_factor,
    get_waste_factor,
    to_kg,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses (lightweight, no DB dependency)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmissionResult:
    """Single emission calculation result."""
    activity_type: str
    scope: int
    source_id: int           # PK of the source category table row
    source_table: str        # e.g. 'electricity'
    emissions_kg_co2e: float
    emissions_metric_tons: float
    factor_used: float
    factor_unit: str
    activity_id: int = 0     # populated after DB write


@dataclass
class CalculationSummary:
    """Aggregated run summary returned by run_all_calculations()."""
    scope1_kg_co2e: float = 0.0
    scope2_kg_co2e: float = 0.0
    scope3_kg_co2e: float = 0.0
    total_kwh: float = 0.0
    total_water_gallons: float = 0.0
    total_waste_kg: float = 0.0
    waste_diversion_rate: float | None = None
    energy_intensity: float | None = None      # kWh per business unit
    records_processed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_kg_co2e(self) -> float:
        return self.scope1_kg_co2e + self.scope2_kg_co2e + self.scope3_kg_co2e

    @property
    def total_metric_tons(self) -> float:
        return self.total_kg_co2e / 1_000.0


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_activity(
    conn,
    parsed_table: str,
    parsed_id: int,
    activity_type: str,
    scope: int,
    location: str | None,
    period_start: Any,
    period_end: Any,
) -> int:
    """
    Insert or update an activity row and return its activity_id.
    If a row already exists for (parsed_table, parsed_id) it is updated in-place.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO activities
                (parsed_table, parsed_id, activity_type, scope, location, period_start, period_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (parsed_table, parsed_id)
                DO UPDATE SET
                    activity_type = EXCLUDED.activity_type,
                    scope         = EXCLUDED.scope,
                    location      = EXCLUDED.location,
                    period_start  = EXCLUDED.period_start,
                    period_end    = EXCLUDED.period_end
            RETURNING activity_id
            """,
            (parsed_table, parsed_id, activity_type, scope, location,
             period_start, period_end),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def _upsert_emission(
    conn,
    activity_id: int,
    emissions_kg_co2e: float,
    factor_used: float,
    factor_unit: str,
) -> None:
    """Insert or update an emission row linked to an activity."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO emissions
                (activity_id, emissions_kg_co2e, emissions_metric_tons, factor_used, factor_unit)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (activity_id)
                DO UPDATE SET
                    emissions_kg_co2e     = EXCLUDED.emissions_kg_co2e,
                    emissions_metric_tons = EXCLUDED.emissions_metric_tons,
                    factor_used           = EXCLUDED.factor_used,
                    factor_unit           = EXCLUDED.factor_unit,
                    calculated_at         = NOW()
            """,
            (
                activity_id,
                round(emissions_kg_co2e, 6),
                round(emissions_kg_co2e / 1_000.0, 6),
                round(factor_used, 8),
                factor_unit,
            ),
        )


def _add_unique_constraint_if_needed(conn) -> None:
    """
    Ensure the activities table has a unique constraint on (parsed_table, parsed_id).
    Runs once; silently skips if already present.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_activities_parsed'
                ) THEN
                    ALTER TABLE activities
                        ADD CONSTRAINT uq_activities_parsed
                        UNIQUE (parsed_table, parsed_id);
                END IF;
            END;
            $$
            """
        )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Purchased Electricity – Scope 2
# Formula: Electricity (kg CO₂e) = kWh × grid_factor
# ─────────────────────────────────────────────────────────────────────────────

def calc_electricity_emissions(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EmissionResult]:
    """
    Process all rows in the ``parsed_electricity`` table (optionally filtered by period)
    and write Scope 2 emission records to ``activities`` + ``emissions``.

    Parameters
    ──────────
    conn         : psycopg2 connection (open, auto-commit off)
    period_start : ISO date string 'YYYY-MM-DD' (inclusive filter, optional)
    period_end   : ISO date string 'YYYY-MM-DD' (inclusive filter, optional)

    Returns
    ───────
    List of EmissionResult, one per electricity record processed.
    """
    results: list[EmissionResult] = []

    query = """
        SELECT parsed_id, kwh, location, period_start, period_end
        FROM parsed_electricity
        WHERE kwh IS NOT NULL AND kwh > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    for row in rows:
        elec_id, kwh, location, p_start, p_end = row
        try:
            factor = get_electricity_factor(location)
            emission_kg = float(kwh) * factor

            activity_id = _upsert_activity(
                conn,
                parsed_table="parsed_electricity",
                parsed_id=elec_id,
                activity_type="purchased_electricity",
                scope=2,
                location=location,
                period_start=p_start,
                period_end=p_end,
            )
            _upsert_emission(
                conn,
                activity_id=activity_id,
                emissions_kg_co2e=emission_kg,
                factor_used=factor,
                factor_unit="kg CO2e/kWh",
            )
            results.append(EmissionResult(
                activity_type="purchased_electricity",
                scope=2,
                source_id=elec_id,
                source_table="parsed_electricity",
                emissions_kg_co2e=emission_kg,
                emissions_metric_tons=emission_kg / 1_000.0,
                factor_used=factor,
                factor_unit="kg CO2e/kWh",
                activity_id=activity_id,
            ))
            logger.debug(
                "Electricity id=%d | %.2f kWh × %.4f = %.2f kg CO₂e",
                elec_id, kwh, factor, emission_kg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Electricity id=%d error: %s", elec_id, exc)

    conn.commit()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stationary Fuel Combustion – Scope 1
# Formula: Fuel Emissions (kg CO₂e) = quantity × fuel_emission_factor
# ─────────────────────────────────────────────────────────────────────────────

def calc_stationary_fuel_emissions(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EmissionResult]:
    """
    Process all rows in the ``parsed_stationary_fuel`` table and write Scope 1
    emission records.

    Supports fuel types: natural_gas, propane, heating_oil.
    Supported units per fuel: therm, gallon, ft3.
    """
    results: list[EmissionResult] = []

    query = """
        SELECT parsed_id, fuel_type, quantity, unit, period_start, period_end
        FROM parsed_stationary_fuel
        WHERE quantity IS NOT NULL AND quantity > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    for row in rows:
        sf_id, fuel_type, quantity, unit, p_start, p_end = row
        try:
            factor = get_stationary_fuel_factor(fuel_type, unit)
            emission_kg = float(quantity) * factor
            factor_unit = f"kg CO2e/{unit or 'therms'}"

            activity_id = _upsert_activity(
                conn,
                parsed_table="parsed_stationary_fuel",
                parsed_id=sf_id,
                activity_type="stationary_fuel_combustion",
                scope=1,
                location=None,
                period_start=p_start,
                period_end=p_end,
            )
            _upsert_emission(conn, activity_id, emission_kg, factor, factor_unit)
            results.append(EmissionResult(
                activity_type="stationary_fuel_combustion",
                scope=1,
                source_id=sf_id,
                source_table="parsed_stationary_fuel",
                emissions_kg_co2e=emission_kg,
                emissions_metric_tons=emission_kg / 1_000.0,
                factor_used=factor,
                factor_unit=factor_unit,
                activity_id=activity_id,
            ))
            logger.debug(
                "Stationary fuel id=%d | %s %.2f %s × %.4f = %.2f kg CO₂e",
                sf_id, fuel_type, quantity, unit, factor, emission_kg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Stationary fuel id=%d error: %s", sf_id, exc)

    conn.commit()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. Vehicle Fuel Use – Scope 1
# Formula: Vehicle Fuel Emissions (kg CO₂e) = quantity × fuel_emission_factor
# ─────────────────────────────────────────────────────────────────────────────

def calc_vehicle_fuel_emissions(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EmissionResult]:
    """
    Process all rows in the ``parsed_vehicle_fuel`` table and write Scope 1 mobile
    combustion emission records.

    Supports fuel types: gasoline, diesel.
    Supported units: gallon, liter.
    """
    results: list[EmissionResult] = []

    query = """
        SELECT parsed_id, fuel_type, quantity, unit, period_start, period_end
        FROM parsed_vehicle_fuel
        WHERE quantity IS NOT NULL AND quantity > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    for row in rows:
        v_id, fuel_type, quantity, unit, p_start, p_end = row
        try:
            factor = get_vehicle_fuel_factor(fuel_type, unit)
            emission_kg = float(quantity) * factor
            factor_unit = f"kg CO2e/{unit or 'gallon'}"

            activity_id = _upsert_activity(
                conn,
                parsed_table="parsed_vehicle_fuel",
                parsed_id=v_id,
                activity_type="vehicle_fuel_use",
                scope=1,
                location=None,
                period_start=p_start,
                period_end=p_end,
            )
            _upsert_emission(conn, activity_id, emission_kg, factor, factor_unit)
            results.append(EmissionResult(
                activity_type="vehicle_fuel_use",
                scope=1,
                source_id=v_id,
                source_table="parsed_vehicle_fuel",
                emissions_kg_co2e=emission_kg,
                emissions_metric_tons=emission_kg / 1_000.0,
                factor_used=factor,
                factor_unit=factor_unit,
                activity_id=activity_id,
            ))
            logger.debug(
                "Vehicle id=%d | %s %.2f %s × %.4f = %.2f kg CO₂e",
                v_id, fuel_type, quantity, unit, factor, emission_kg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Vehicle id=%d error: %s", v_id, exc)

    conn.commit()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 4. Transportation & Shipping – Scope 3
# Formula:
#   ton_miles = weight_tons × distance_miles
#   Shipping Emissions (kg CO₂e) = ton_miles × transport_mode_factor
# ─────────────────────────────────────────────────────────────────────────────

def calc_shipping_emissions(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EmissionResult]:
    """
    Process all rows in the ``shipping`` table and write Scope 3 transportation
    emission records.

    The ``parsed_shipping`` table already stores weight in tons and distance in miles
    (converted at ingest time).  Transport mode defaults to 'truck'.
    """
    results: list[EmissionResult] = []

    query = """
        SELECT parsed_id, weight_tons, distance_miles, transport_mode, period_start, period_end
        FROM parsed_shipping
        WHERE weight_tons IS NOT NULL AND distance_miles IS NOT NULL
          AND weight_tons > 0 AND distance_miles > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    for row in rows:
        sh_id, weight_tons, distance_miles, mode, p_start, p_end = row
        try:
            ton_miles = float(weight_tons) * float(distance_miles)
            factor = get_transport_factor(mode)
            emission_kg = ton_miles * factor
            factor_unit = f"kg CO2e/ton-mile ({mode or 'truck'})"

            activity_id = _upsert_activity(
                conn,
                parsed_table="parsed_shipping",
                parsed_id=sh_id,
                activity_type="transportation_shipping",
                scope=3,
                location=None,
                period_start=p_start,
                period_end=p_end,
            )
            _upsert_emission(conn, activity_id, emission_kg, factor, factor_unit)
            results.append(EmissionResult(
                activity_type="transportation_shipping",
                scope=3,
                source_id=sh_id,
                source_table="parsed_shipping",
                emissions_kg_co2e=emission_kg,
                emissions_metric_tons=emission_kg / 1_000.0,
                factor_used=factor,
                factor_unit=factor_unit,
                activity_id=activity_id,
            ))
            logger.debug(
                "Shipping id=%d | %.2f t × %.1f mi = %.1f ton-mi × %.4f = %.2f kg CO₂e",
                sh_id, weight_tons, distance_miles, ton_miles, factor, emission_kg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Shipping id=%d error: %s", sh_id, exc)

    conn.commit()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 5. Waste Generation – Scope 3
# Formula: Waste Emissions (kg CO₂e) = waste_kg × disposal_method_factor
# ─────────────────────────────────────────────────────────────────────────────

def calc_waste_emissions(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EmissionResult]:
    """
    Process all rows in the ``parsed_waste`` table and write Scope 3 waste
    generation emission records.

    Units 'lb' / 'lbs' are automatically converted to kg before applying the
    emission factor.  Disposal methods: landfill, recycle, compost, incinerate.
    """
    results: list[EmissionResult] = []

    query = """
        SELECT parsed_id, waste_weight, unit, disposal_method, period_start, period_end
        FROM parsed_waste
        WHERE waste_weight IS NOT NULL AND waste_weight > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    for row in rows:
        w_id, waste_weight, unit, disposal_method, p_start, p_end = row
        try:
            waste_kg = to_kg(float(waste_weight), unit or "kg")
            factor = get_waste_factor(disposal_method)
            emission_kg = waste_kg * factor
            factor_unit = f"kg CO2e/kg waste ({disposal_method or 'landfill'})"

            activity_id = _upsert_activity(
                conn,
                parsed_table="parsed_waste",
                parsed_id=w_id,
                activity_type="waste_generation",
                scope=3,
                location=None,
                period_start=p_start,
                period_end=p_end,
            )
            _upsert_emission(conn, activity_id, emission_kg, factor, factor_unit)
            results.append(EmissionResult(
                activity_type="waste_generation",
                scope=3,
                source_id=w_id,
                source_table="parsed_waste",
                emissions_kg_co2e=emission_kg,
                emissions_metric_tons=emission_kg / 1_000.0,
                factor_used=factor,
                factor_unit=factor_unit,
                activity_id=activity_id,
            ))
            logger.debug(
                "Waste id=%d | %.2f kg × %.4f (%s) = %.2f kg CO₂e",
                w_id, waste_kg, factor, disposal_method, emission_kg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Waste id=%d error: %s", w_id, exc)

    conn.commit()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 6. Water Usage – Non-GHG Resource Metric
# Calculation: sum of water_volume within period; store in water_metrics
# ─────────────────────────────────────────────────────────────────────────────

def calc_water_metrics(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, Any]:
    """
    Aggregate water consumption from the ``parsed_water`` table for the given period
    and write a summary row to ``water_metrics``.

    Volumes reported in gallons (gal) and cubic metres (m³) are kept separate.
    For reporting, m³ is converted to gallons (1 m³ = 264.172 gal).

    Also registers each water row as a non-GHG activity in the ``activities``
    table so it appears in dashboards.

    Returns a dict with total_water_gallons, total_water_m3, record_count.
    """
    query = """
        SELECT parsed_id, water_volume, unit, location, period_start, period_end
        FROM parsed_water
        WHERE water_volume IS NOT NULL AND water_volume > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    total_gallons = 0.0
    total_m3 = 0.0

    for row in rows:
        w_id, water_volume, unit, location, p_start, p_end = row
        vol = float(water_volume)
        u = (unit or "gal").lower().replace(" ", "").replace("³", "3")

        if u in ("gal", "gallon", "gallons"):
            total_gallons += vol
            canonical_unit = "gallon"
        elif u in ("m3", "m³", "cubicmeter", "cubicmetre"):
            total_m3 += vol
            total_gallons += vol * 264.172  # keep running gallon total
            canonical_unit = "m3"
        else:
            # fallback – treat as gallons
            total_gallons += vol
            canonical_unit = "gallon"

        # Register in activities (non-GHG, scope=None represented as water_usage)
        _upsert_activity(
            conn,
            parsed_table="parsed_water",
            parsed_id=w_id,
            activity_type="water_usage",
            scope=3,          # Reported under Scope 3 for framework alignment
            location=location,
            period_start=p_start,
            period_end=p_end,
        )

    if rows:
        # Derive effective period bounds from row data when not explicitly provided
        eff_start = period_start
        eff_end = period_end
        if not eff_start:
            dates = [r[4] for r in rows if r[4] is not None]
            eff_start = min(dates) if dates else None
        if not eff_end:
            dates = [r[5] for r in rows if r[5] is not None]
            eff_end = max(dates) if dates else None
        # Final fallback: use today so NOT NULL constraint is satisfied
        from datetime import date as _date
        if eff_start is None:
            eff_start = _date.today()
        if eff_end is None:
            eff_end = _date.today()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO water_metrics
                    (period_start, period_end, total_water_volume, unit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (eff_start, eff_end, round(total_gallons, 4), "gallon"),
            )

    conn.commit()
    return {
        "total_water_gallons": round(total_gallons, 4),
        "total_water_m3": round(total_m3, 4),
        "record_count": len(rows),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Energy Intensity – Derived Metric
# Formula: Energy Intensity = Total kWh ÷ Business Activity Unit
# ─────────────────────────────────────────────────────────────────────────────

def calc_energy_intensity(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    denominator_type: str = "employees",
    denominator_value: float,
) -> dict[str, Any]:
    """
    Calculate Energy Intensity for a given period and business unit denominator.

    Parameters
    ──────────
    denominator_type  : 'employees', 'revenue', 'shipments', 'sqft', etc.
    denominator_value : The numeric value of the denominator (e.g. 25 employees).

    Returns a dict with total_kwh, energy_intensity_value, and unit string.

    Example:  18,000 kWh ÷ 25 employees = 720.0 kWh/employee
    """
    if denominator_value <= 0:
        raise ValueError("denominator_value must be > 0")

    query = """
        SELECT COALESCE(SUM(kwh), 0.0)
        FROM parsed_electricity
        WHERE kwh IS NOT NULL
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        total_kwh = float(cur.fetchone()[0])

    intensity = total_kwh / denominator_value
    intensity_unit = f"kWh/{denominator_type}"

    # Derive effective period bounds from parsed_electricity when not provided
    eff_start = period_start
    eff_end = period_end
    if not eff_start or not eff_end:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MIN(period_start), MAX(period_end) FROM parsed_electricity "
                "WHERE kwh IS NOT NULL"
            )
            bounds = cur.fetchone()
            if not eff_start and bounds and bounds[0]:
                eff_start = bounds[0]
            if not eff_end and bounds and bounds[1]:
                eff_end = bounds[1]
    from datetime import date as _date
    if eff_start is None:
        eff_start = _date.today()
    if eff_end is None:
        eff_end = _date.today()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO energy_metrics
                (period_start, period_end, total_kwh, denominator_type,
                 denominator_value, energy_intensity_value, energy_intensity_unit)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                eff_start,
                eff_end,
                round(total_kwh, 4),
                denominator_type,
                round(denominator_value, 6),
                round(intensity, 6),
                intensity_unit,
            ),
        )

    conn.commit()
    logger.debug(
        "Energy intensity: %.2f kWh ÷ %.2f %s = %.2f %s",
        total_kwh, denominator_value, denominator_type, intensity, intensity_unit,
    )
    return {
        "total_kwh": round(total_kwh, 4),
        "denominator_type": denominator_type,
        "denominator_value": denominator_value,
        "energy_intensity_value": round(intensity, 4),
        "energy_intensity_unit": intensity_unit,
        "period_start": period_start,
        "period_end": period_end,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Waste Diversion Rate – Derived Metric
# Formula: (Recycled + Composted) ÷ Total Waste Generated
# ─────────────────────────────────────────────────────────────────────────────

def calc_waste_diversion_rate(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, Any]:
    """
    Aggregate waste data from ``parsed_waste`` and compute the diversion rate.

    All weights are normalised to kg before aggregation.
    Writes a summary row to ``waste_metrics``.

    Returns a dict with total_waste_kg, recycled_kg, composted_kg,
    landfill_kg, diversion_rate (0–1), and diversion_pct (0–100).

    Example: (300 kg recycled + 0 composted) ÷ 420 kg total = 71.4 %
    """
    query = """
        SELECT waste_weight, unit, disposal_method
        FROM parsed_waste
        WHERE waste_weight IS NOT NULL AND waste_weight > 0
    """
    params: list[Any] = []
    if period_start:
        query += " AND (period_start >= %s OR period_start IS NULL)"
        params.append(period_start)
    if period_end:
        query += " AND (period_end <= %s OR period_end IS NULL)"
        params.append(period_end)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    totals: dict[str, float] = {
        "landfill": 0.0,
        "recycle": 0.0,
        "compost": 0.0,
        "incinerate": 0.0,
    }

    for waste_weight, unit, disposal_method in rows:
        kg = to_kg(float(waste_weight), unit or "kg")
        method = (disposal_method or "landfill").lower().strip()
        bucket = method if method in totals else "landfill"
        totals[bucket] += kg

    total_kg = sum(totals.values())
    recycled_kg = totals["recycle"]
    composted_kg = totals["compost"]
    diverted_kg = recycled_kg + composted_kg

    diversion_rate = (diverted_kg / total_kg) if total_kg > 0 else None

    if rows:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO waste_metrics
                    (period_start, period_end, total_waste_kg,
                     recycled_waste_kg, composted_waste_kg, diversion_rate)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    period_start,
                    period_end,
                    round(total_kg, 4),
                    round(recycled_kg, 4),
                    round(composted_kg, 4),
                    round(diversion_rate, 6) if diversion_rate is not None else None,
                ),
            )
        conn.commit()

    logger.debug(
        "Waste diversion: %.2f kg recycled + %.2f kg composted / %.2f kg total = %s%%",
        recycled_kg, composted_kg, total_kg,
        f"{diversion_rate*100:.1f}" if diversion_rate is not None else "N/A",
    )
    return {
        "total_waste_kg": round(total_kg, 4),
        "landfill_kg": round(totals["landfill"], 4),
        "recycled_kg": round(recycled_kg, 4),
        "composted_kg": round(composted_kg, 4),
        "incinerated_kg": round(totals["incinerate"], 4),
        "diverted_kg": round(diverted_kg, 4),
        "diversion_rate": round(diversion_rate, 6) if diversion_rate is not None else None,
        "diversion_pct": round(diversion_rate * 100, 2) if diversion_rate is not None else None,
        "record_count": len(rows),
        "period_start": period_start,
        "period_end": period_end,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. GHG Summary – Total Scope 1 / 2 / 3 and Grand Total
# ─────────────────────────────────────────────────────────────────────────────

def calc_ghg_summary(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict[str, Any]:
    """
    Query the ``emissions`` + ``activities`` tables to return a scope-level
    GHG summary for the given period.

    This is a READ-ONLY derived view — no new rows are written.

    Returns
    ───────
    {
      "scope1_kg_co2e": ...,  "scope1_metric_tons": ...,
      "scope2_kg_co2e": ...,  "scope2_metric_tons": ...,
      "scope3_kg_co2e": ...,  "scope3_metric_tons": ...,
      "total_kg_co2e":  ...,  "total_metric_tons":  ...,
      "by_activity_type": { <type>: kg_co2e, ... }
    }
    """
    scope_query = """
        SELECT
            a.scope,
            COALESCE(SUM(e.emissions_kg_co2e), 0)     AS total_kg,
            COALESCE(SUM(e.emissions_metric_tons), 0)  AS total_mt
        FROM activities a
        JOIN emissions e ON e.activity_id = a.activity_id
        WHERE a.scope IS NOT NULL
    """
    type_query = """
        SELECT
            a.activity_type,
            COALESCE(SUM(e.emissions_kg_co2e), 0)     AS total_kg
        FROM activities a
        JOIN emissions e ON e.activity_id = a.activity_id
    """
    period_clauses: list[str] = []
    params: list[Any] = []
    if period_start:
        period_clauses.append("(a.period_start >= %s OR a.period_start IS NULL)")
        params.append(period_start)
    if period_end:
        period_clauses.append("(a.period_end <= %s OR a.period_end IS NULL)")
        params.append(period_end)

    where_fragment = (" AND " + " AND ".join(period_clauses)) if period_clauses else ""
    scope_query += where_fragment + " GROUP BY a.scope ORDER BY a.scope"
    type_query += (" WHERE " + " AND ".join(period_clauses)) if period_clauses else ""
    type_query += " GROUP BY a.activity_type ORDER BY total_kg DESC"

    scope_map: dict[int, tuple[float, float]] = {}
    with conn.cursor() as cur:
        cur.execute(scope_query, params)
        for scope, total_kg, total_mt in cur.fetchall():
            scope_map[int(scope)] = (float(total_kg), float(total_mt))

    activity_map: dict[str, float] = {}
    with conn.cursor() as cur:
        cur.execute(type_query, params)
        for atype, total_kg in cur.fetchall():
            activity_map[atype] = float(total_kg)

    s1_kg, s1_mt = scope_map.get(1, (0.0, 0.0))
    s2_kg, s2_mt = scope_map.get(2, (0.0, 0.0))
    s3_kg, s3_mt = scope_map.get(3, (0.0, 0.0))
    total_kg = s1_kg + s2_kg + s3_kg

    summary = {
        "scope1_kg_co2e":     round(s1_kg, 4),
        "scope1_metric_tons": round(s1_mt, 6),
        "scope2_kg_co2e":     round(s2_kg, 4),
        "scope2_metric_tons": round(s2_mt, 6),
        "scope3_kg_co2e":     round(s3_kg, 4),
        "scope3_metric_tons": round(s3_mt, 6),
        "total_kg_co2e":      round(total_kg, 4),
        "total_metric_tons":  round(total_kg / 1_000.0, 6),
        "by_activity_type":   {k: round(v, 4) for k, v in activity_map.items()},
        "period_start":       period_start,
        "period_end":         period_end,
    }
    logger.info(
        "GHG summary | Scope1=%.2f Scope2=%.2f Scope3=%.2f Total=%.2f kg CO₂e",
        s1_kg, s2_kg, s3_kg, total_kg,
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 10. Water Intensity – Derived Metric
# Formula: Water Intensity = Total Water Used ÷ Business Activity Unit
# ─────────────────────────────────────────────────────────────────────────────

def calc_water_intensity(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    denominator_type: str = "employees",
    denominator_value: float,
) -> dict[str, Any]:
    """
    Calculate Water Intensity (water volume per business unit).

    Example: 18,000 gal ÷ 25 employees = 720 gal/employee

    Returns dict with total_water_gallons, intensity_value, and unit string.
    """
    if denominator_value <= 0:
        raise ValueError("denominator_value must be > 0")

    water_result = calc_water_metrics(
        conn, period_start=period_start, period_end=period_end
    )
    total_gallons = water_result["total_water_gallons"]
    intensity = total_gallons / denominator_value

    return {
        "total_water_gallons": round(total_gallons, 4),
        "denominator_type": denominator_type,
        "denominator_value": denominator_value,
        "water_intensity_value": round(intensity, 4),
        "water_intensity_unit": f"gal/{denominator_type}",
        "period_start": period_start,
        "period_end": period_end,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. Orchestrator – run all calculations for a period
# ─────────────────────────────────────────────────────────────────────────────

def run_all_calculations(
    conn,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    energy_denominator_type: str | None = None,
    energy_denominator_value: float | None = None,
    water_denominator_type: str | None = None,
    water_denominator_value: float | None = None,
) -> CalculationSummary:
    """
    Run all emission and sustainability metric calculations for a time period.

    Executes in this order:
      1. Scope 2 – Purchased Electricity
      2. Scope 1 – Stationary Fuel Combustion
      3. Scope 1 – Vehicle Fuel Use
      4. Scope 3 – Transportation & Shipping
      5. Scope 3 – Waste Generation
      6. Water Usage (non-GHG)
      7. Waste Diversion Rate (derived)
      8. Energy Intensity (derived, only if denominator provided)
      9. GHG Summary (read-only aggregation)

    Parameters
    ──────────
    conn                       : Open psycopg2 connection
    period_start               : 'YYYY-MM-DD' filter start (optional)
    period_end                 : 'YYYY-MM-DD' filter end (optional)
    energy_denominator_type    : e.g. 'employees'  – enables energy intensity
    energy_denominator_value   : numeric value for energy intensity denominator
    water_denominator_type     : e.g. 'employees'  – enables water intensity
    water_denominator_value    : numeric value for water intensity denominator

    Returns a CalculationSummary with aggregated totals and any errors.
    """
    summary = CalculationSummary()

    # Ensure unique constraint exists (idempotent)
    try:
        _add_unique_constraint_if_needed(conn)
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        logger.warning("Could not ensure unique constraint on activities: %s", exc)

    # ── Scope 2: Electricity ──────────────────────────────────────────────
    try:
        elec_results = calc_electricity_emissions(
            conn, period_start=period_start, period_end=period_end
        )
        total_kwh_this_run = 0.0
        for r in elec_results:
            summary.scope2_kg_co2e += r.emissions_kg_co2e
            summary.records_processed += 1
        # Collect kWh from DB for energy intensity (separate query)
        with conn.cursor() as cur:
            p: list[Any] = []
            q = "SELECT COALESCE(SUM(kwh), 0) FROM parsed_electricity WHERE kwh IS NOT NULL"
            if period_start:
                q += " AND (period_start >= %s OR period_start IS NULL)"
                p.append(period_start)
            if period_end:
                q += " AND (period_end <= %s OR period_end IS NULL)"
                p.append(period_end)
            cur.execute(q, p)
            summary.total_kwh = float(cur.fetchone()[0])
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"electricity: {exc}")
        logger.error("Electricity calc failed: %s", exc)

    # ── Scope 1: Stationary Fuel ──────────────────────────────────────────
    try:
        sf_results = calc_stationary_fuel_emissions(
            conn, period_start=period_start, period_end=period_end
        )
        for r in sf_results:
            summary.scope1_kg_co2e += r.emissions_kg_co2e
            summary.records_processed += 1
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"stationary_fuel: {exc}")
        logger.error("Stationary fuel calc failed: %s", exc)

    # ── Scope 1: Vehicle Fuel ─────────────────────────────────────────────
    try:
        veh_results = calc_vehicle_fuel_emissions(
            conn, period_start=period_start, period_end=period_end
        )
        for r in veh_results:
            summary.scope1_kg_co2e += r.emissions_kg_co2e
            summary.records_processed += 1
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"vehicles: {exc}")
        logger.error("Vehicle fuel calc failed: %s", exc)

    # ── Scope 3: Shipping ─────────────────────────────────────────────────
    try:
        sh_results = calc_shipping_emissions(
            conn, period_start=period_start, period_end=period_end
        )
        for r in sh_results:
            summary.scope3_kg_co2e += r.emissions_kg_co2e
            summary.records_processed += 1
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"shipping: {exc}")
        logger.error("Shipping calc failed: %s", exc)

    # ── Scope 3: Waste ────────────────────────────────────────────────────
    try:
        wst_results = calc_waste_emissions(
            conn, period_start=period_start, period_end=period_end
        )
        for r in wst_results:
            summary.scope3_kg_co2e += r.emissions_kg_co2e
            summary.records_processed += 1
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"waste_emissions: {exc}")
        logger.error("Waste emission calc failed: %s", exc)

    # ── Water Usage ───────────────────────────────────────────────────────
    try:
        water_result = calc_water_metrics(
            conn, period_start=period_start, period_end=period_end
        )
        summary.total_water_gallons = water_result["total_water_gallons"]
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"water_metrics: {exc}")
        logger.error("Water metrics calc failed: %s", exc)

    # ── Waste Diversion Rate ──────────────────────────────────────────────
    try:
        diversion = calc_waste_diversion_rate(
            conn, period_start=period_start, period_end=period_end
        )
        summary.total_waste_kg = diversion["total_waste_kg"]
        summary.waste_diversion_rate = diversion["diversion_rate"]
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        summary.errors.append(f"waste_diversion: {exc}")
        logger.error("Waste diversion calc failed: %s", exc)

    # ── Energy Intensity (optional) ───────────────────────────────────────
    if energy_denominator_type and energy_denominator_value:
        try:
            ei = calc_energy_intensity(
                conn,
                period_start=period_start,
                period_end=period_end,
                denominator_type=energy_denominator_type,
                denominator_value=float(energy_denominator_value),
            )
            summary.energy_intensity = ei["energy_intensity_value"]
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            summary.errors.append(f"energy_intensity: {exc}")
            logger.error("Energy intensity calc failed: %s", exc)

    logger.info(
        "run_all_calculations complete | "
        "Scope1=%.2f Scope2=%.2f Scope3=%.2f Total=%.2f kg CO₂e | "
        "Records=%d Errors=%d",
        summary.scope1_kg_co2e,
        summary.scope2_kg_co2e,
        summary.scope3_kg_co2e,
        summary.total_kg_co2e,
        summary.records_processed,
        len(summary.errors),
    )
    return summary
