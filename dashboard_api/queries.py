"""
queries.py – Aggregation queries that compute KPI and chart data from
the populated parsed_* tables by applying emission factors inline via SQL
CASE expressions.

All tCO2e values are computed as (quantity × factor_kg) / 1000.
"""
from __future__ import annotations

from . import db
from .emission_factors import (
    ELECTRICITY_KG_PER_KWH,
    STATIONARY_FUEL_KG,
    VEHICLE_FUEL_KG,
    SHIPPING_KG_PER_TON_MILE,
    WASTE_KG_PER_KG,
    GALLON_TO_M3,
    LB_TO_KG,
)

# ─── helpers ──────────────────────────────────────────────────────────────

def _stationary_case() -> str:
    """
    SQL CASE expression that returns kg CO2e for one parsed_stationary_fuel row.
    """
    lines = []
    for fuel, units in STATIONARY_FUEL_KG.items():
        for unit, factor in units.items():
            lines.append(
                f"WHEN fuel_type = '{fuel}' AND unit = '{unit}' "
                f"THEN quantity * {factor}"
            )
    lines.append("ELSE 0")
    return "CASE " + " ".join(lines) + " END"


def _vehicle_case() -> str:
    lines = []
    for fuel, units in VEHICLE_FUEL_KG.items():
        for unit, factor in units.items():
            lines.append(
                f"WHEN fuel_type = '{fuel}' AND unit = '{unit}' "
                f"THEN quantity * {factor}"
            )
    lines.append("ELSE 0")
    return "CASE " + " ".join(lines) + " END"


def _shipping_case() -> str:
    lines = []
    for mode, factor in SHIPPING_KG_PER_TON_MILE.items():
        if mode is None:
            continue
        lines.append(
            f"WHEN transport_mode = '{mode}' "
            f"THEN weight_tons * distance_miles * {factor}"
        )
    default = SHIPPING_KG_PER_TON_MILE[None]
    lines.append(f"ELSE weight_tons * distance_miles * {default}")
    return "CASE " + " ".join(lines) + " END"


def _waste_case() -> str:
    lines = []
    for method, factor in WASTE_KG_PER_KG.items():
        waste_factor = f"""
            CASE unit
              WHEN 'lb' THEN waste_weight * {LB_TO_KG} * {factor}
              ELSE waste_weight * {factor}
            END
        """
        lines.append(f"WHEN disposal_method = '{method}' THEN {waste_factor}")
    lines.append("ELSE 0")
    return "CASE " + " ".join(lines) + " END"


# ─── public API ───────────────────────────────────────────────────────────

def get_kpis() -> dict:
    """
    Return top-level KPI values:
      - total_emissions_tco2e
      - energy_kwh (total electricity consumed)
      - water_m3
      - waste_diversion_rate (0-100 float)
      - sparkline: list of {period, tco2e} for the Total Emissions card
    """
    # --- total emissions by source (tCO2e) ---
    elec_tco2e = db.scalar(
        f"SELECT COALESCE(SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000, 0) FROM parsed_electricity"
    ) or 0.0

    stat_tco2e = db.scalar(
        f"SELECT COALESCE(SUM({_stationary_case()}) / 1000, 0) FROM parsed_stationary_fuel"
    ) or 0.0

    veh_tco2e = db.scalar(
        f"SELECT COALESCE(SUM({_vehicle_case()}) / 1000, 0) FROM parsed_vehicle_fuel"
    ) or 0.0

    ship_tco2e = db.scalar(
        f"SELECT COALESCE(SUM({_shipping_case()}) / 1000, 0) FROM parsed_shipping"
    ) or 0.0

    waste_tco2e = db.scalar(
        f"SELECT COALESCE(SUM({_waste_case()}) / 1000, 0) FROM parsed_waste"
    ) or 0.0

    total = float(elec_tco2e) + float(stat_tco2e) + float(veh_tco2e) + float(ship_tco2e) + float(waste_tco2e)

    # --- energy intensity (total kWh) ---
    energy_kwh = float(
        db.scalar("SELECT COALESCE(SUM(kwh), 0) FROM parsed_electricity") or 0.0
    )

    # --- water (m3) ---
    water_rows = db.query(
        "SELECT water_volume, unit FROM parsed_water WHERE water_volume IS NOT NULL"
    )
    water_m3 = 0.0
    for row in water_rows:
        vol = float(row["water_volume"] or 0)
        if row["unit"] == "gallon":
            water_m3 += vol * GALLON_TO_M3
        else:
            water_m3 += vol

    # --- waste diversion rate ---
    waste_all = db.query(
        "SELECT waste_weight, unit, disposal_method FROM parsed_waste"
    )
    total_waste_kg = 0.0
    diverted_kg = 0.0
    for row in waste_all:
        wt = float(row["waste_weight"] or 0)
        kg = wt * LB_TO_KG if row["unit"] == "lb" else wt
        total_waste_kg += kg
        if row["disposal_method"] in ("recycle", "compost"):
            diverted_kg += kg
    diversion_rate = (diverted_kg / total_waste_kg * 100) if total_waste_kg > 0 else 0.0

    # --- sparkline: monthly total emissions ---
    sparkline = _sparkline()

    return {
        "total_emissions_tco2e": round(total, 2),
        "energy_kwh": round(energy_kwh, 2),
        "water_m3": round(water_m3, 2),
        "waste_diversion_rate": round(diversion_rate, 1),
        "sparkline": sparkline,
    }


def _sparkline() -> list[dict]:
    """
    Aggregate monthly emissions across all sources for the sparkline.
    Combines electricity + stationary + vehicle + shipping + waste
    grouped by (year, month) of period_start.
    """
    results: dict[str, float] = {}

    def add(rows: list[dict], key: str) -> None:
        for row in rows:
            period = str(row.get("period") or "")
            results[period] = results.get(period, 0.0) + float(row.get("tco2e") or 0)

    add(
        db.query(
            f"""
            SELECT to_char(period_start, 'YYYY-MM') AS period,
                   SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000 AS tco2e
            FROM parsed_electricity
            WHERE period_start IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        "tco2e",
    )
    add(
        db.query(
            f"""
            SELECT to_char(period_start, 'YYYY-MM') AS period,
                   SUM({_stationary_case()}) / 1000 AS tco2e
            FROM parsed_stationary_fuel
            WHERE period_start IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        "tco2e",
    )
    add(
        db.query(
            f"""
            SELECT to_char(period_start, 'YYYY-MM') AS period,
                   SUM({_vehicle_case()}) / 1000 AS tco2e
            FROM parsed_vehicle_fuel
            WHERE period_start IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        "tco2e",
    )
    add(
        db.query(
            f"""
            SELECT to_char(period_start, 'YYYY-MM') AS period,
                   SUM({_shipping_case()}) / 1000 AS tco2e
            FROM parsed_shipping
            WHERE period_start IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        "tco2e",
    )
    add(
        db.query(
            f"""
            SELECT to_char(period_start, 'YYYY-MM') AS period,
                   SUM({_waste_case()}) / 1000 AS tco2e
            FROM parsed_waste
            WHERE period_start IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        "tco2e",
    )

    return [
        {"period": k, "tco2e": round(v, 4)}
        for k, v in sorted(results.items())
        if k
    ]


def get_emissions_by_scope() -> list[dict]:
    """
    Return tCO2e per GHG scope for the doughnut chart.
    Scope 1 = stationary + vehicle; Scope 2 = electricity; Scope 3 = shipping + waste.
    """
    stat_tco2e = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_stationary_case()}) / 1000, 0) FROM parsed_stationary_fuel"
        ) or 0
    )
    veh_tco2e = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_vehicle_case()}) / 1000, 0) FROM parsed_vehicle_fuel"
        ) or 0
    )
    elec_tco2e = float(
        db.scalar(
            f"SELECT COALESCE(SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000, 0) FROM parsed_electricity"
        ) or 0
    )
    ship_tco2e = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_shipping_case()}) / 1000, 0) FROM parsed_shipping"
        ) or 0
    )
    waste_tco2e = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_waste_case()}) / 1000, 0) FROM parsed_waste"
        ) or 0
    )

    return [
        {"scope": "Scope 1", "label": "Scope 1 (Direct)", "tco2e": round(stat_tco2e + veh_tco2e, 4)},
        {"scope": "Scope 2", "label": "Scope 2 (Electricity)", "tco2e": round(elec_tco2e, 4)},
        {"scope": "Scope 3", "label": "Scope 3 (Value Chain)", "tco2e": round(ship_tco2e + waste_tco2e, 4)},
    ]


def get_emissions_by_source() -> list[dict]:
    """
    Return tCO2e per emission source for the horizontal bar chart.
    """
    elec = float(
        db.scalar(
            f"SELECT COALESCE(SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000, 0) FROM parsed_electricity"
        ) or 0
    )
    stat = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_stationary_case()}) / 1000, 0) FROM parsed_stationary_fuel"
        ) or 0
    )
    vehicle = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_vehicle_case()}) / 1000, 0) FROM parsed_vehicle_fuel"
        ) or 0
    )
    shipping = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_shipping_case()}) / 1000, 0) FROM parsed_shipping"
        ) or 0
    )
    waste = float(
        db.scalar(
            f"SELECT COALESCE(SUM({_waste_case()}) / 1000, 0) FROM parsed_waste"
        ) or 0
    )

    sources = [
        {"source": "Electricity", "scope": 2, "tco2e": round(elec, 4)},
        {"source": "Stationary Fuel", "scope": 1, "tco2e": round(stat, 4)},
        {"source": "Vehicle Fuel", "scope": 1, "tco2e": round(vehicle, 4)},
        {"source": "Shipping", "scope": 3, "tco2e": round(shipping, 4)},
        {"source": "Waste", "scope": 3, "tco2e": round(waste, 4)},
    ]
    return sorted(sources, key=lambda x: x["tco2e"], reverse=True)


_STATIC_RECOMMENDATIONS = [
    {
        "id": 1,
        "title": "Optimize Shipping Routes",
        "description": "Consolidate freight shipments and switch to rail where available to reduce Scope 3 transport emissions by an estimated 15–20%.",
        "priority": "high",
        "category": "shipping",
        "potential_saving_tco2e": None,
    },
    {
        "id": 2,
        "title": "Switch to LED Lighting",
        "description": "Replacing existing lighting with LED fixtures across all facilities could reduce electricity consumption by up to 30%, lowering Scope 2 emissions.",
        "priority": "medium",
        "category": "electricity",
        "potential_saving_tco2e": None,
    },
]


def get_recommendations() -> list[dict]:
    """
    Return recommendations from DB if populated; otherwise fall back to the
    static list of two items for the dashboard demo.
    """
    rows = db.query(
        """
        SELECT r.recommendation_id AS id,
               r.recommendation_text AS description,
               a.activity_type AS category
        FROM recommendations r
        LEFT JOIN activities a ON a.activity_id = r.activity_id
        ORDER BY r.recommendation_id
        LIMIT 10
        """
    )
    if rows:
        return [
            {
                "id": row["id"],
                "title": row.get("category", "Recommendation").replace("_", " ").title(),
                "description": row["description"],
                "priority": "medium",
                "category": row.get("category") or "general",
            }
            for row in rows
        ]
    return _STATIC_RECOMMENDATIONS
