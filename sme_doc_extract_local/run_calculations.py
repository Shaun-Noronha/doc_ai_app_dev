"""
run_calculations.py – Standalone runner that skips document extraction/parsing
and runs the emissions + sustainability metric calculations directly against
the already-populated parsed tables.

Usage
──────
# Dry-run: prints all calculated values, writes NOTHING to DB
python run_calculations.py --dry-run

# Live run: calculates and writes results to DB
python run_calculations.py

# Filter to a specific billing period
python run_calculations.py --period-start 2024-01-01 --period-end 2024-12-31

# Include energy + water intensity (needs a business unit denominator)
python run_calculations.py --denominator-type employees --denominator-value 25

# Dry-run with period filter
python run_calculations.py --dry-run --period-start 2024-01-01 --period-end 2024-12-31
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ── make sure `src` is importable when running from sme_doc_extract_local/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

# Load .env from both possible locations (same logic as config.py)
_here = Path(__file__).resolve().parent
for _env_path in (_here / ".env", _here.parent / ".env"):
    if _env_path.exists():
        load_dotenv(_env_path)
        break

from src.db import get_connection
from src.calculations import (
    calc_electricity_emissions,
    calc_stationary_fuel_emissions,
    calc_vehicle_fuel_emissions,
    calc_shipping_emissions,
    calc_waste_emissions,
    calc_water_metrics,
    calc_energy_intensity,
    calc_waste_diversion_rate,
    calc_ghg_summary,
    run_all_calculations,
    EmissionResult,
)

# ── Logging: INFO to stdout so every step is visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SEP = "─" * 70


def _print_emission_results(label: str, results: list[EmissionResult]) -> None:
    if not results:
        print(f"  [no rows found in source table]")
        return
    print(f"  {'ID':>6}  {'kg CO₂e':>12}  {'tCO₂e':>10}  {'Factor':>10}  Unit")
    print(f"  {'──':>6}  {'──────':>12}  {'─────':>10}  {'──────':>10}  ────")
    for r in results:
        print(
            f"  {r.source_id:>6}  "
            f"{r.emissions_kg_co2e:>12.4f}  "
            f"{r.emissions_metric_tons:>10.6f}  "
            f"{r.factor_used:>10.4f}  "
            f"{r.factor_unit}"
        )
    total_kg = sum(r.emissions_kg_co2e for r in results)
    print(f"  {'TOTAL':>6}  {total_kg:>12.4f} kg CO₂e  ({total_kg/1000:.4f} tCO₂e)")


def dry_run(conn, period_start, period_end, denominator_type, denominator_value):
    """
    Run every calculation function, print results to stdout, then ROLLBACK
    so nothing is written to the database.
    """
    print()
    print("=" * 70)
    print("  DRY-RUN MODE — no data will be written to the database")
    print("=" * 70)

    # ── 1. Scope 2: Electricity ──────────────────────────────────────────────
    print()
    print(SEP)
    print("  SCOPE 2 | Purchased Electricity  (source table: parsed_electricity)")
    print(SEP)
    elec = calc_electricity_emissions(conn, period_start=period_start, period_end=period_end)
    _print_emission_results("Electricity", elec)
    conn.rollback()

    # ── 2. Scope 1: Stationary Fuel ──────────────────────────────────────────
    print()
    print(SEP)
    print("  SCOPE 1 | Stationary Fuel Combustion  (source table: parsed_stationary_fuel)")
    print(SEP)
    sf = calc_stationary_fuel_emissions(conn, period_start=period_start, period_end=period_end)
    _print_emission_results("Stationary Fuel", sf)
    conn.rollback()

    # ── 3. Scope 1: Vehicle Fuel ─────────────────────────────────────────────
    print()
    print(SEP)
    print("  SCOPE 1 | Vehicle Fuel Use  (source table: parsed_vehicle_fuel)")
    print(SEP)
    veh = calc_vehicle_fuel_emissions(conn, period_start=period_start, period_end=period_end)
    _print_emission_results("Vehicle Fuel", veh)
    conn.rollback()

    # ── 4. Scope 3: Shipping ─────────────────────────────────────────────────
    print()
    print(SEP)
    print("  SCOPE 3 | Transportation & Shipping  (source table: parsed_shipping)")
    print(SEP)
    sh = calc_shipping_emissions(conn, period_start=period_start, period_end=period_end)
    _print_emission_results("Shipping", sh)
    conn.rollback()

    # ── 5. Scope 3: Waste ────────────────────────────────────────────────────
    print()
    print(SEP)
    print("  SCOPE 3 | Waste Generation  (source table: parsed_waste)")
    print(SEP)
    wst = calc_waste_emissions(conn, period_start=period_start, period_end=period_end)
    _print_emission_results("Waste", wst)
    conn.rollback()

    # ── 6. Water (non-GHG) ───────────────────────────────────────────────────
    print()
    print(SEP)
    print("  RESOURCE | Water Usage  (source table: parsed_water)")
    print(SEP)
    water = calc_water_metrics(conn, period_start=period_start, period_end=period_end)
    print(f"  Total water (gallons) : {water['total_water_gallons']:,.2f}")
    print(f"  Total water (m³)      : {water['total_water_m3']:,.2f}")
    print(f"  Records found         : {water['record_count']}")
    conn.rollback()

    # ── 7. Waste Diversion Rate ──────────────────────────────────────────────
    print()
    print(SEP)
    print("  DERIVED | Waste Diversion Rate  (source table: parsed_waste)")
    print(SEP)
    wd = calc_waste_diversion_rate(conn, period_start=period_start, period_end=period_end)
    print(f"  Total waste (kg)      : {wd['total_waste_kg']:,.4f}")
    print(f"  Landfill (kg)         : {wd['landfill_kg']:,.4f}")
    print(f"  Recycled (kg)         : {wd['recycled_kg']:,.4f}")
    print(f"  Composted (kg)        : {wd['composted_kg']:,.4f}")
    print(f"  Diverted (kg)         : {wd['diverted_kg']:,.4f}")
    diversion = wd['diversion_pct']
    print(f"  Diversion rate        : {f'{diversion:.2f}%' if diversion is not None else 'N/A (no waste data)'}")
    conn.rollback()

    # ── 8. Energy Intensity (optional) ──────────────────────────────────────
    if denominator_value and denominator_value > 0:
        print()
        print(SEP)
        print(f"  DERIVED | Energy Intensity  (÷ {denominator_value} {denominator_type})")
        print(SEP)
        ei = calc_energy_intensity(
            conn,
            period_start=period_start,
            period_end=period_end,
            denominator_type=denominator_type,
            denominator_value=denominator_value,
        )
        print(f"  Total kWh             : {ei['total_kwh']:,.2f}")
        print(f"  Denominator           : {ei['denominator_value']} {ei['denominator_type']}")
        print(f"  Energy intensity      : {ei['energy_intensity_value']:,.4f} {ei['energy_intensity_unit']}")
        conn.rollback()

    # ── Summary totals (calculated from in-memory results, no DB read) ──────
    s1 = sum(r.emissions_kg_co2e for r in sf + veh)
    s2 = sum(r.emissions_kg_co2e for r in elec)
    s3 = sum(r.emissions_kg_co2e for r in sh + wst)
    total = s1 + s2 + s3

    print()
    print("=" * 70)
    print("  GHG SUMMARY (dry-run totals — not yet saved)")
    print("=" * 70)
    print(f"  Scope 1 (direct)      : {s1:>12.4f} kg CO₂e  ({s1/1000:.4f} tCO₂e)")
    print(f"  Scope 2 (electricity) : {s2:>12.4f} kg CO₂e  ({s2/1000:.4f} tCO₂e)")
    print(f"  Scope 3 (indirect)    : {s3:>12.4f} kg CO₂e  ({s3/1000:.4f} tCO₂e)")
    print(f"  {'TOTAL':21} : {total:>12.4f} kg CO₂e  ({total/1000:.4f} tCO₂e)")
    print()
    print("  Nothing was written to the database.")
    print("  Run without --dry-run to commit results.")
    print()


def live_run(conn, period_start, period_end, denominator_type, denominator_value):
    """
    Run all calculations and write results to the database.
    Prints a rich summary after committing.
    """
    print()
    print("=" * 70)
    print("  LIVE RUN — results will be written to the database")
    print("=" * 70)
    print()

    summary = run_all_calculations(
        conn,
        period_start=period_start,
        period_end=period_end,
        energy_denominator_type=denominator_type if denominator_value else None,
        energy_denominator_value=float(denominator_value) if denominator_value else None,
    )

    # ── per-activity breakdown via ghg_summary ───────────────────────────────
    print()
    print(SEP)
    print("  RESULTS WRITTEN TO DB — GHG breakdown by activity type")
    print(SEP)
    ghg = calc_ghg_summary(conn, period_start=period_start, period_end=period_end)
    if ghg["by_activity_type"]:
        print(f"  {'Activity Type':35}  {'kg CO₂e':>12}")
        print(f"  {'─'*35}  {'──────':>12}")
        for atype, kg in ghg["by_activity_type"].items():
            print(f"  {atype:35}  {kg:>12.4f}")
    else:
        print("  [no emission records found — check your parsed tables have data]")

    print()
    print("=" * 70)
    print("  FINAL GHG TOTALS (committed to emissions table)")
    print("=" * 70)
    print(f"  Scope 1 (direct)      : {ghg['scope1_kg_co2e']:>12.4f} kg CO₂e  ({ghg['scope1_metric_tons']:.4f} tCO₂e)")
    print(f"  Scope 2 (electricity) : {ghg['scope2_kg_co2e']:>12.4f} kg CO₂e  ({ghg['scope2_metric_tons']:.4f} tCO₂e)")
    print(f"  Scope 3 (indirect)    : {ghg['scope3_kg_co2e']:>12.4f} kg CO₂e  ({ghg['scope3_metric_tons']:.4f} tCO₂e)")
    print(f"  {'TOTAL':21} : {ghg['total_kg_co2e']:>12.4f} kg CO₂e  ({ghg['total_metric_tons']:.4f} tCO₂e)")

    if summary.total_water_gallons > 0:
        print()
        print(f"  Water usage           : {summary.total_water_gallons:>12.2f} gallons")
    if summary.total_waste_kg > 0:
        dr = summary.waste_diversion_rate
        print(f"  Total waste           : {summary.total_waste_kg:>12.4f} kg")
        print(f"  Waste diversion rate  : {f'{dr*100:.2f}%' if dr is not None else 'N/A'}")
    if summary.energy_intensity is not None:
        print(f"  Energy intensity      : {summary.energy_intensity:>12.4f} kWh/{denominator_type}")

    if summary.errors:
        print()
        print("  WARNINGS / ERRORS:")
        for e in summary.errors:
            print(f"    ✗ {e}")

    print()
    print(f"  Records processed : {summary.records_processed}")
    print(f"  Errors            : {len(summary.errors)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Run GHG + sustainability calculations from parsed DB tables."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print calculated values without writing anything to the database.",
    )
    parser.add_argument(
        "--period-start", default=None, metavar="YYYY-MM-DD",
        help="Only include parsed records on or after this date.",
    )
    parser.add_argument(
        "--period-end", default=None, metavar="YYYY-MM-DD",
        help="Only include parsed records on or before this date.",
    )
    parser.add_argument(
        "--denominator-type", default="employees",
        help="Business unit label for energy/water intensity (default: employees).",
    )
    parser.add_argument(
        "--denominator-value", type=float, default=None,
        help="Numeric value of the business unit (e.g. 25). "
             "Required to calculate energy/water intensity.",
    )
    parser.add_argument(
        "--database-url", default=None,
        help="PostgreSQL connection string. Defaults to DATABASE_URL env var.",
    )
    args = parser.parse_args()

    # ── Resolve DATABASE_URL ─────────────────────────────────────────────────
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            "ERROR: No DATABASE_URL found.\n"
            "Set it in your .env file or pass --database-url 'postgresql://...'"
        )
        sys.exit(1)

    log.info("Connecting to database…")
    try:
        conn = get_connection(database_url)
    except Exception as exc:
        print(f"ERROR: Could not connect to database: {exc}")
        sys.exit(1)

    log.info("Connected.")
    if args.period_start or args.period_end:
        log.info("Period filter: %s → %s", args.period_start or "any", args.period_end or "any")

    try:
        if args.dry_run:
            dry_run(
                conn,
                period_start=args.period_start,
                period_end=args.period_end,
                denominator_type=args.denominator_type,
                denominator_value=args.denominator_value,
            )
        else:
            live_run(
                conn,
                period_start=args.period_start,
                period_end=args.period_end,
                denominator_type=args.denominator_type,
                denominator_value=args.denominator_value,
            )
    finally:
        conn.close()
        log.info("Connection closed.")


if __name__ == "__main__":
    main()
