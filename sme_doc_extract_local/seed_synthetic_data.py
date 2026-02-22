"""
Seed synthetic data for monthly analysis across all tables except vendors.

Inserts 24 months (2024-01 through 2025-12) of:
- documents + parsed_electricity, parsed_stationary_fuel, parsed_vehicle_fuel,
  parsed_shipping, parsed_waste, parsed_water
- activities + emissions (GHG sources only; water has activity but no emission)
- recommendations (subset of activities)
- energy_metrics, water_metrics, waste_metrics (one row per month)

Uses same emission factors as dashboard (EPA/DEFRA) so KPIs and sparklines match.
Safe to re-run: does not truncate; additive. Run after schema is applied.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from repo root (parent of sme_doc_extract_local)
_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Add it to .env at repo root.")

# Emission factors (kg CO2e per unit) – aligned with dashboard_api/emission_factors.py
ELECTRICITY_KG_PER_KWH = 0.3862
STATIONARY_FUEL_KG = {
    "natural_gas": {"therm": 5.3067, "ft3": 0.0549, "gallon": 5.3067},
    "propane": {"gallon": 5.7260, "therm": 6.3200, "ft3": 0.0680},
    "heating_oil": {"gallon": 10.1530, "therm": 7.4100, "ft3": 0.0001},
}
VEHICLE_FUEL_KG = {
    "gasoline": {"gallon": 8.8878, "liter": 2.3480},
    "diesel": {"gallon": 10.1800, "liter": 2.6893},
}
SHIPPING_KG_PER_TON_MILE = {"truck": 0.1693, "ship": 0.0098, "rail": 0.0229, "air": 1.1300, None: 0.1693}
WASTE_KG_PER_KG = {"landfill": 0.4460, "incinerate": 0.0980, "recycle": 0.0, "compost": 0.01}
LB_TO_KG = 0.453592

# Synthetic data bounds (enough for monthly sparklines)
MONTHS_START = date(2024, 1, 1)
MONTHS_END = date(2025, 12, 1)
DENOMINATOR_EMPLOYEES = 25


def _month_range():
    y, m = MONTHS_START.year, MONTHS_START.month
    end_y, end_m = MONTHS_END.year, MONTHS_END.month
    while (y, m) <= (end_y, end_m):
        yield date(y, m, 1)
        m += 1
        if m > 12:
            m = 1
            y += 1


def _period_end(period_start: date) -> date:
    """Last day of the month."""
    if period_start.month == 12:
        return date(period_start.year + 1, 1, 1) - __import__("datetime").timedelta(days=1)
    return date(period_start.year, period_start.month + 1, 1) - __import__("datetime").timedelta(days=1)


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            counts = {
                "documents": 0,
                "parsed_electricity": 0,
                "parsed_stationary_fuel": 0,
                "parsed_vehicle_fuel": 0,
                "parsed_shipping": 0,
                "parsed_waste": 0,
                "parsed_water": 0,
                "activities": 0,
                "emissions": 0,
                "recommendations": 0,
                "energy_metrics": 0,
                "water_metrics": 0,
                "waste_metrics": 0,
            }
            activity_ids_for_recs = []

            for period_start in _month_range():
                period_end = _period_end(period_start)
                ps, pe = period_start.isoformat(), period_end.isoformat()

                # ─── Documents + parsed_* ─────────────────────────────────────
                # Electricity
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('utility_bill', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic", "period": ps}), f"syn_electricity_{ps}.pdf"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                kwh = 1200.0 + (period_start.month % 12) * 80
                cur.execute(
                    """
                    INSERT INTO parsed_electricity (document_id, kwh, unit, location, period_start, period_end)
                    VALUES (%s, %s, 'kWh', 'CA', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, kwh, period_start, period_end),
                )
                elec_parsed_id = cur.fetchone()[0]
                counts["parsed_electricity"] += 1

                # Stationary fuel (natural gas, therms)
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('utility_bill', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic"}), f"syn_gas_{ps}.pdf"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                therms = 80.0 + (period_start.month % 6) * 15
                cur.execute(
                    """
                    INSERT INTO parsed_stationary_fuel (document_id, fuel_type, quantity, unit, period_start, period_end)
                    VALUES (%s, 'natural_gas', %s, 'therm', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, therms, period_start, period_end),
                )
                stat_parsed_id = cur.fetchone()[0]
                counts["parsed_stationary_fuel"] += 1

                # Vehicle fuel (gasoline, gallons)
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('vehicle_fuel_csv_import', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic"}), f"syn_vehicle_{ps}.csv"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                gallons = 90.0 + (period_start.month % 5) * 10
                cur.execute(
                    """
                    INSERT INTO parsed_vehicle_fuel (document_id, fuel_type, quantity, unit, period_start, period_end)
                    VALUES (%s, 'gasoline', %s, 'gallon', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, gallons, period_start, period_end),
                )
                veh_parsed_id = cur.fetchone()[0]
                counts["parsed_vehicle_fuel"] += 1

                # Shipping (truck, ton-miles)
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('delivery_receipt', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic"}), f"syn_freight_{ps}.pdf"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                weight_tons = 2.5 + (period_start.month % 4) * 0.5
                distance_miles = 200.0 + (period_start.month % 10) * 30
                cur.execute(
                    """
                    INSERT INTO parsed_shipping (document_id, weight_tons, distance_miles, transport_mode, period_start, period_end)
                    VALUES (%s, %s, %s, 'truck', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, weight_tons, distance_miles, period_start, period_end),
                )
                ship_parsed_id = cur.fetchone()[0]
                counts["parsed_shipping"] += 1

                # Waste: landfill + recycle (two rows per month)
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('waste_invoice', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic"}), f"syn_waste_{ps}.pdf"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                waste_landfill_kg = 400.0 + (period_start.month % 8) * 25
                waste_recycle_kg = 150.0 + (period_start.month % 5) * 20
                cur.execute(
                    """
                    INSERT INTO parsed_waste (document_id, waste_weight, unit, disposal_method, period_start, period_end)
                    VALUES (%s, %s, 'kg', 'landfill', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, waste_landfill_kg, period_start, period_end),
                )
                waste_parsed_id_1 = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO parsed_waste (document_id, waste_weight, unit, disposal_method, period_start, period_end)
                    VALUES (%s, %s, 'kg', 'recycle', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, waste_recycle_kg, period_start, period_end),
                )
                waste_parsed_id_2 = cur.fetchone()[0]
                counts["parsed_waste"] += 2

                # Water
                cur.execute(
                    """
                    INSERT INTO documents (document_type, exported_json, source_filename)
                    VALUES ('utility_bill', %s::jsonb, %s)
                    RETURNING document_id
                    """,
                    (json.dumps({"source": "synthetic"}), f"syn_water_{ps}.pdf"),
                )
                doc_id = cur.fetchone()[0]
                counts["documents"] += 1
                water_gal = 8000.0 + (period_start.month % 12) * 200
                cur.execute(
                    """
                    INSERT INTO parsed_water (document_id, water_volume, unit, location, period_start, period_end)
                    VALUES (%s, %s, 'gallon', 'CA', %s, %s)
                    RETURNING parsed_id
                    """,
                    (doc_id, water_gal, period_start, period_end),
                )
                water_parsed_id = cur.fetchone()[0]
                counts["parsed_water"] += 1

                # ─── Activities + emissions ─────────────────────────────────────
                def insert_activity(parsed_table: str, parsed_id: int, activity_type: str, scope: int | None, loc: str | None):
                    cur.execute(
                        """
                        INSERT INTO activities (parsed_table, parsed_id, activity_type, scope, location, period_start, period_end)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (parsed_table, parsed_id)
                        DO UPDATE SET period_start = EXCLUDED.period_start, period_end = EXCLUDED.period_end
                        RETURNING activity_id
                        """,
                        (parsed_table, parsed_id, activity_type, scope, loc, period_start, period_end),
                    )
                    return cur.fetchone()[0]

                def insert_emission(activity_id: int, kg_co2e: float, factor: float, factor_unit: str):
                    cur.execute(
                        """
                        INSERT INTO emissions (activity_id, emissions_kg_co2e, emissions_metric_tons, factor_used, factor_unit)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (activity_id)
                        DO UPDATE SET emissions_kg_co2e = EXCLUDED.emissions_kg_co2e,
                                        emissions_metric_tons = EXCLUDED.emissions_metric_tons,
                                        factor_used = EXCLUDED.factor_used,
                                        factor_unit = EXCLUDED.factor_unit,
                                        calculated_at = NOW()
                        """,
                        (activity_id, round(kg_co2e, 6), round(kg_co2e / 1000.0, 6), round(factor, 8), factor_unit),
                    )

                # Electricity
                a_id = insert_activity("parsed_electricity", elec_parsed_id, "purchased_electricity", 2, "CA")
                counts["activities"] += 1
                insert_emission(a_id, kwh * ELECTRICITY_KG_PER_KWH, ELECTRICITY_KG_PER_KWH, "kg CO2e/kWh")
                counts["emissions"] += 1
                activity_ids_for_recs.append((a_id, 0))  # for rec text index

                # Stationary fuel
                a_id = insert_activity("parsed_stationary_fuel", stat_parsed_id, "stationary_fuel_combustion", 1, None)
                counts["activities"] += 1
                factor = STATIONARY_FUEL_KG["natural_gas"]["therm"]
                insert_emission(a_id, therms * factor, factor, "kg CO2e/therm")
                counts["emissions"] += 1

                # Vehicle fuel
                a_id = insert_activity("parsed_vehicle_fuel", veh_parsed_id, "vehicle_fuel_use", 1, None)
                counts["activities"] += 1
                factor = VEHICLE_FUEL_KG["gasoline"]["gallon"]
                insert_emission(a_id, gallons * factor, factor, "kg CO2e/gallon")
                counts["emissions"] += 1

                # Shipping
                a_id = insert_activity("parsed_shipping", ship_parsed_id, "transportation_shipping", 3, None)
                counts["activities"] += 1
                factor = SHIPPING_KG_PER_TON_MILE["truck"]
                ton_miles = weight_tons * distance_miles
                insert_emission(a_id, ton_miles * factor, factor, "kg CO2e/ton-mile (truck)")
                counts["emissions"] += 1
                activity_ids_for_recs.append((a_id, 1))

                # Waste (landfill)
                a_id = insert_activity("parsed_waste", waste_parsed_id_1, "waste_generation", 3, None)
                counts["activities"] += 1
                factor = WASTE_KG_PER_KG["landfill"]
                insert_emission(a_id, waste_landfill_kg * factor, factor, "kg CO2e/kg waste (landfill)")
                counts["emissions"] += 1
                activity_ids_for_recs.append((a_id, 2))

                # Waste (recycle) – activity + emission (0 factor)
                a_id = insert_activity("parsed_waste", waste_parsed_id_2, "waste_generation", 3, None)
                counts["activities"] += 1
                factor = WASTE_KG_PER_KG["recycle"]
                insert_emission(a_id, waste_recycle_kg * factor, factor, "kg CO2e/kg waste (recycle)")
                counts["emissions"] += 1

                # Water (activity only; no emission)
                insert_activity("parsed_water", water_parsed_id, "water_usage", 3, "CA")
                counts["activities"] += 1

                # ─── Metrics (one per month) ───────────────────────────────────
                total_kwh_month = kwh
                intensity = total_kwh_month / DENOMINATOR_EMPLOYEES
                cur.execute(
                    """
                    INSERT INTO energy_metrics
                    (period_start, period_end, total_kwh, denominator_type, denominator_value,
                     energy_intensity_value, energy_intensity_unit)
                    VALUES (%s, %s, %s, 'employees', %s, %s, 'kWh/employees')
                    """,
                    (period_start, period_end, round(total_kwh_month, 4), DENOMINATOR_EMPLOYEES, round(intensity, 6)),
                )
                counts["energy_metrics"] += 1

                cur.execute(
                    """
                    INSERT INTO water_metrics (period_start, period_end, total_water_volume, unit)
                    VALUES (%s, %s, %s, 'gallon')
                    """,
                    (period_start, period_end, round(water_gal, 4)),
                )
                counts["water_metrics"] += 1

                total_waste_kg = waste_landfill_kg + waste_recycle_kg
                diverted = waste_recycle_kg  # recycle only in this seed
                diversion_rate = (diverted / total_waste_kg) if total_waste_kg > 0 else 0
                cur.execute(
                    """
                    INSERT INTO waste_metrics
                    (period_start, period_end, total_waste_kg, recycled_waste_kg, composted_waste_kg, diversion_rate)
                    VALUES (%s, %s, %s, %s, 0, %s)
                    """,
                    (period_start, period_end, round(total_waste_kg, 4), round(waste_recycle_kg, 4), round(diversion_rate, 6)),
                )
                counts["waste_metrics"] += 1

            # ─── Recommendations: one per month, rotating category ─────────────────
            rec_texts = [
                "Consider switching to a green electricity tariff to reduce Scope 2 emissions.",
                "Optimize route planning to reduce freight ton-miles and consider rail for long hauls.",
                "Increase recycling and composting to improve waste diversion and lower Scope 3 emissions.",
            ]
            for i, (activity_id, text_idx) in enumerate(activity_ids_for_recs):
                if i % 3 == 0:  # one recommendation per month (every 3rd entry is electricity)
                    cur.execute(
                        "INSERT INTO recommendations (activity_id, recommendation_text) VALUES (%s, %s)",
                        (activity_id, rec_texts[text_idx % len(rec_texts)]),
                    )
                    counts["recommendations"] += 1

        conn.commit()
        print("Synthetic data seeded successfully (all tables except vendors).")
        for table, n in counts.items():
            print(f"  {table}: {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
