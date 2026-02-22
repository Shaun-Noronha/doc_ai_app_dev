"""
queries.py – Aggregation queries that compute KPI and chart data from
the populated parsed_* tables by applying emission factors inline via SQL
CASE expressions.

All tCO2e values are computed as (quantity × factor_kg) / 1000.

Refresh path: build_dashboard_payload(conn) runs all aggregations over one
connection and returns the full payload; refresh_snapshot() writes it to
dashboard_snapshot. Read path: get_dashboard() returns the cached payload.
"""
from __future__ import annotations

import json
from decimal import Decimal

from psycopg2.extras import RealDictCursor

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


def _cur_scalar(cur, sql: str, params: tuple = (), default=None):
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return default
    # RealDictCursor returns dict-like rows; use first value
    if hasattr(row, "values"):
        return next(iter(row.values()))
    return row[0]


def _cur_query(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _sparkline_sql() -> str:
    """Single SQL that UNIONs all five source period/tco2e subqueries and groups by period."""
    return f"""
        SELECT to_char(period, 'YYYY-MM') AS period, SUM(tco2e) AS tco2e
        FROM (
            SELECT period_start AS period, (kwh * {ELECTRICITY_KG_PER_KWH}) / 1000 AS tco2e
            FROM parsed_electricity WHERE period_start IS NOT NULL
            UNION ALL
            SELECT period_start, ({_stationary_case()}) / 1000 FROM parsed_stationary_fuel WHERE period_start IS NOT NULL
            UNION ALL
            SELECT period_start, ({_vehicle_case()}) / 1000 FROM parsed_vehicle_fuel WHERE period_start IS NOT NULL
            UNION ALL
            SELECT period_start, ({_shipping_case()}) / 1000 FROM parsed_shipping WHERE period_start IS NOT NULL
            UNION ALL
            SELECT period_start, ({_waste_case()}) / 1000 FROM parsed_waste WHERE period_start IS NOT NULL
        ) u
        GROUP BY 1 ORDER BY 1
    """


def _run_sparkline(cur) -> list[dict]:
    """Run the single sparkline query and return [{"period": "YYYY-MM", "tco2e": float}, ...]."""
    rows = _cur_query(cur, _sparkline_sql())
    return [{"period": str(row.get("period") or ""), "tco2e": round(float(row.get("tco2e") or 0), 4)} for row in rows if row.get("period")]


def get_documents_all() -> list[dict]:
    """Return all documents that have at least one parsed_* row (same shape as by-scope)."""
    sql = """
        SELECT DISTINCT d.document_id, d.document_type, d.source_filename, d.created_at
        FROM documents d
        WHERE d.document_id IN (SELECT document_id FROM parsed_electricity)
           OR d.document_id IN (SELECT document_id FROM parsed_stationary_fuel)
           OR d.document_id IN (SELECT document_id FROM parsed_vehicle_fuel)
           OR d.document_id IN (SELECT document_id FROM parsed_shipping)
           OR d.document_id IN (SELECT document_id FROM parsed_waste)
           OR d.document_id IN (SELECT document_id FROM parsed_water)
        ORDER BY d.created_at DESC
        LIMIT 500
    """
    rows = db.query(sql)
    return [
        {
            "document_id": row["document_id"],
            "document_type": row["document_type"] or "document",
            "source_filename": row["source_filename"] or "",
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        }
        for row in rows
    ]


def _documents_from_rows(rows: list[dict]) -> list[dict]:
    """Convert document rows to API shape."""
    return [
        {
            "document_id": row["document_id"],
            "document_type": row["document_type"] or "document",
            "source_filename": row["source_filename"] or "",
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        }
        for row in rows
    ]


def get_documents_by_scope(scope: int) -> list[dict]:
    """
    Return documents that contribute to the given scope.
    Uses document_scope view (scope 0=water, 1=fuel, 2=electricity, 3=shipping/waste).
    Same shape as dashboard documents: document_id, document_type, source_filename, created_at.
    """
    if scope not in (0, 1, 2, 3):
        return []
    rows = db.query(
        """
        SELECT DISTINCT d.document_id, d.document_type, d.source_filename, d.created_at
        FROM documents d
        JOIN document_scope ds ON d.document_id = ds.document_id
        WHERE ds.scope = %s
        ORDER BY d.created_at DESC
        LIMIT 500
        """,
        (scope,),
    )
    return _documents_from_rows(rows)


def _documents_by_scope_cur(cur, scope: int) -> list[dict]:
    """Run documents-by-scope query on the given cursor (uses document_scope view)."""
    if scope not in (0, 1, 2, 3):
        return []
    cur.execute(
        """
        SELECT DISTINCT d.document_id, d.document_type, d.source_filename, d.created_at
        FROM documents d
        JOIN document_scope ds ON d.document_id = ds.document_id
        WHERE ds.scope = %s
        ORDER BY d.created_at DESC
        LIMIT 500
        """,
        (scope,),
    )
    return _documents_from_rows([dict(r) for r in cur.fetchall()])


def build_dashboard_payload(conn) -> dict:
    """
    Build full dashboard payload (kpis, emissions_by_scope, emissions_by_source,
    recommendations) using a single connection. Used by refresh_snapshot().
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Emission totals (compute once, reuse for kpis + scope + source)
        elec_tco2e = float(
            _cur_scalar(cur, f"SELECT COALESCE(SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000, 0) FROM parsed_electricity") or 0
        )
        stat_tco2e = float(
            _cur_scalar(cur, f"SELECT COALESCE(SUM({_stationary_case()}) / 1000, 0) FROM parsed_stationary_fuel") or 0
        )
        veh_tco2e = float(
            _cur_scalar(cur, f"SELECT COALESCE(SUM({_vehicle_case()}) / 1000, 0) FROM parsed_vehicle_fuel") or 0
        )
        ship_tco2e = float(
            _cur_scalar(cur, f"SELECT COALESCE(SUM({_shipping_case()}) / 1000, 0) FROM parsed_shipping") or 0
        )
        waste_tco2e = float(
            _cur_scalar(cur, f"SELECT COALESCE(SUM({_waste_case()}) / 1000, 0) FROM parsed_waste") or 0
        )
        total_tco2e = elec_tco2e + stat_tco2e + veh_tco2e + ship_tco2e + waste_tco2e

        # Energy
        energy_kwh = float(_cur_scalar(cur, "SELECT COALESCE(SUM(kwh), 0) FROM parsed_electricity") or 0)

        # Water
        water_rows = _cur_query(cur, "SELECT water_volume, unit FROM parsed_water WHERE water_volume IS NOT NULL")
        water_m3 = 0.0
        for row in water_rows:
            vol = float(row["water_volume"] or 0)
            water_m3 += vol * GALLON_TO_M3 if row["unit"] == "gallon" else vol

        # Waste diversion
        waste_rows = _cur_query(cur, "SELECT waste_weight, unit, disposal_method FROM parsed_waste")
        total_waste_kg = 0.0
        diverted_kg = 0.0
        for row in waste_rows:
            wt = float(row["waste_weight"] or 0)
            kg = wt * LB_TO_KG if row["unit"] == "lb" else wt
            total_waste_kg += kg
            if row["disposal_method"] in ("recycle", "compost"):
                diverted_kg += kg
        diversion_rate = (diverted_kg / total_waste_kg * 100) if total_waste_kg > 0 else 0.0

        # Scope totals (for metrics)
        scope_1_tco2e = round(stat_tco2e + veh_tco2e, 4)
        scope_2_tco2e = round(elec_tco2e, 4)
        scope_3_tco2e = round(ship_tco2e + waste_tco2e, 4)
        water_volume_gallons = round(water_m3 * 264.172, 2) if water_m3 else 0.0

        # Sparkline / monthly tCO2e (single query)
        sparkline = _run_sparkline(cur)

        # Documents that contributed data (have at least one parsed_* row)
        doc_rows = _cur_query(
            cur,
            """
            SELECT DISTINCT d.document_id, d.document_type, d.source_filename, d.created_at
            FROM documents d
            WHERE d.document_id IN (SELECT document_id FROM parsed_electricity)
               OR d.document_id IN (SELECT document_id FROM parsed_stationary_fuel)
               OR d.document_id IN (SELECT document_id FROM parsed_vehicle_fuel)
               OR d.document_id IN (SELECT document_id FROM parsed_shipping)
               OR d.document_id IN (SELECT document_id FROM parsed_waste)
               OR d.document_id IN (SELECT document_id FROM parsed_water)
            ORDER BY d.created_at DESC
            LIMIT 500
            """,
        )
        documents = [
            {
                "document_id": row["document_id"],
                "document_type": row["document_type"] or "document",
                "source_filename": row["source_filename"] or "",
                "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            }
            for row in doc_rows
        ]

        kpis = {
            "total_emissions_tco2e": round(total_tco2e, 2),
            "energy_kwh": round(energy_kwh, 2),
            "water_m3": round(water_m3, 2),
            "waste_diversion_rate": round(diversion_rate, 1),
            "sparkline": sparkline,
        }

        metrics = {
            "scope_1_tco2e": scope_1_tco2e,
            "scope_2_tco2e": scope_2_tco2e,
            "scope_3_tco2e": scope_3_tco2e,
            "water_usage": {
                "volume_m3": round(water_m3, 4),
                "volume_gallons": water_volume_gallons,
            },
        }

        emissions_by_scope = [
            {"scope": "Scope 1", "label": "Scope 1 (Direct)", "tco2e": round(stat_tco2e + veh_tco2e, 4)},
            {"scope": "Scope 2", "label": "Scope 2 (Electricity)", "tco2e": round(elec_tco2e, 4)},
            {"scope": "Scope 3", "label": "Scope 3 (Value Chain)", "tco2e": round(ship_tco2e + waste_tco2e, 4)},
        ]

        sources = [
            {"source": "Electricity", "scope": 2, "tco2e": round(elec_tco2e, 4)},
            {"source": "Stationary Fuel", "scope": 1, "tco2e": round(stat_tco2e, 4)},
            {"source": "Vehicle Fuel", "scope": 1, "tco2e": round(veh_tco2e, 4)},
            {"source": "Shipping", "scope": 3, "tco2e": round(ship_tco2e, 4)},
            {"source": "Waste", "scope": 3, "tco2e": round(waste_tco2e, 4)},
        ]
        emissions_by_source = sorted(sources, key=lambda x: x["tco2e"], reverse=True)

        # Recommendations
        rec_rows = _cur_query(
            cur,
            """
            SELECT r.recommendation_id AS id, r.recommendation_text AS description,
                   a.activity_type AS category, r.criteria, r.saving_kg_co2e, r.score
            FROM recommendations r
            LEFT JOIN activities a ON a.activity_id = r.activity_id
            ORDER BY r.score DESC NULLS LAST LIMIT 15
            """,
        )
        if rec_rows:
            recommendations = [
                {
                    "id": row["id"],
                    "title": (row.get("criteria") or row.get("category") or "Recommendation").replace("_", " ").title(),
                    "description": row["description"],
                    "priority": (
                        "high" if row.get("saving_kg_co2e") is not None and float(row["saving_kg_co2e"]) > 50
                        else "medium" if row.get("saving_kg_co2e") is not None and float(row["saving_kg_co2e"]) > 10
                        else "low"
                    ),
                    "category": row.get("criteria") or row.get("category") or "general",
                    "potential_saving_tco2e": round(float(row["saving_kg_co2e"]) / 1000, 4) if row.get("saving_kg_co2e") else None,
                }
                for row in rec_rows
            ]
        else:
            recommendations = _STATIC_RECOMMENDATIONS

    return {
        "kpis": kpis,
        "metrics": metrics,
        "emissions_by_scope": emissions_by_scope,
        "emissions_by_source": emissions_by_source,
        "documents": documents,
        "recommendations": recommendations,
    }


def refresh_snapshot() -> None:
    """Compute dashboard payload once and write to dashboard_snapshot (one connection)."""
    def do_refresh(conn):
        payload = build_dashboard_payload(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_snapshot (id, payload, refreshed_at)
                VALUES (1, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, refreshed_at = NOW()
                """,
                (json.dumps(payload),),
            )
        conn.commit()

    db.with_connection(do_refresh)


def get_scope_payload(scope: int) -> dict:
    """
    Lightweight payload for Scope 1, 2, or 3 view: scopeTotal, bySource, sparkline, documents.
    Uses 3-5 targeted queries instead of full dashboard build.
    """
    if scope not in (1, 2, 3):
        return {"scopeTotal": 0.0, "bySource": [], "sparkline": [], "documents": []}

    def _build(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if scope == 1:
                stat_tco2e = float(_cur_scalar(cur, f"SELECT COALESCE(SUM({_stationary_case()}) / 1000, 0) FROM parsed_stationary_fuel") or 0)
                veh_tco2e = float(_cur_scalar(cur, f"SELECT COALESCE(SUM({_vehicle_case()}) / 1000, 0) FROM parsed_vehicle_fuel") or 0)
                scope_total = round(stat_tco2e + veh_tco2e, 4)
                by_source = [
                    {"source": "Stationary Fuel", "scope": 1, "tco2e": round(stat_tco2e, 4)},
                    {"source": "Vehicle Fuel", "scope": 1, "tco2e": round(veh_tco2e, 4)},
                ]
                by_source = sorted(by_source, key=lambda x: x["tco2e"], reverse=True)
            elif scope == 2:
                elec_tco2e = float(_cur_scalar(cur, f"SELECT COALESCE(SUM(kwh * {ELECTRICITY_KG_PER_KWH}) / 1000, 0) FROM parsed_electricity") or 0)
                scope_total = round(elec_tco2e, 4)
                by_source = [{"source": "Electricity", "scope": 2, "tco2e": round(elec_tco2e, 4)}]
            else:  # scope == 3
                ship_tco2e = float(_cur_scalar(cur, f"SELECT COALESCE(SUM({_shipping_case()}) / 1000, 0) FROM parsed_shipping") or 0)
                waste_tco2e = float(_cur_scalar(cur, f"SELECT COALESCE(SUM({_waste_case()}) / 1000, 0) FROM parsed_waste") or 0)
                scope_total = round(ship_tco2e + waste_tco2e, 4)
                by_source = [
                    {"source": "Shipping", "scope": 3, "tco2e": round(ship_tco2e, 4)},
                    {"source": "Waste", "scope": 3, "tco2e": round(waste_tco2e, 4)},
                ]
                by_source = sorted(by_source, key=lambda x: x["tco2e"], reverse=True)

            sparkline = _run_sparkline(cur)
            documents = _documents_by_scope_cur(cur, scope)
            return {
                "scopeTotal": scope_total,
                "bySource": by_source,
                "sparkline": sparkline,
                "documents": documents,
            }

    return db.with_connection(_build)


def get_water_payload() -> dict:
    """
    Lightweight payload for Water view: water_usage, sparkline, documents.
    Uses 3 queries only.
    """
    def _build(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            water_rows = _cur_query(cur, "SELECT water_volume, unit FROM parsed_water WHERE water_volume IS NOT NULL")
            water_m3 = 0.0
            for row in water_rows:
                vol = float(row["water_volume"] or 0)
                water_m3 += vol * GALLON_TO_M3 if row["unit"] == "gallon" else vol
            water_volume_gallons = round(water_m3 * 264.172, 2) if water_m3 else 0.0
            water_usage = {"volume_m3": round(water_m3, 4), "volume_gallons": water_volume_gallons}

            sparkline = _run_sparkline(cur)
            documents = _documents_by_scope_cur(cur, 0)
            return {"water_usage": water_usage, "sparkline": sparkline, "documents": documents}

    return db.with_connection(_build)


def _make_json_serializable(obj):
    """Recursively convert Decimal and other non-JSON types so FastAPI can serialize."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    return obj


def get_dashboard() -> dict | None:
    """
    Return cached dashboard payload from dashboard_snapshot, or None if missing/empty.
    One query, one connection. Returns None if table does not exist (schema not applied).
    """
    try:
        rows = db.query(
            "SELECT payload FROM dashboard_snapshot WHERE id = 1 AND payload != '{}'::jsonb"
        )
    except Exception:
        # e.g. relation "dashboard_snapshot" does not exist
        return None
    if not rows:
        return None
    raw = rows[0].get("payload")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if isinstance(raw, dict):
        return _make_json_serializable(raw)
    return None


def get_dashboard_live() -> dict:
    """
    Build dashboard payload from parsed_* tables (live). Used when snapshot is empty
    so new data (e.g. after seed) is visible without calling POST /api/refresh.
    """
    def _build(conn):
        return build_dashboard_payload(conn)
    return db.with_connection(_build)


# ─── public API (read from snapshot when available; else live for backward compat) ───

def get_kpis() -> dict:
    """
    Return top-level KPI values. Uses cached snapshot when available.
    """
    cached = get_dashboard()
    if cached and "kpis" in cached:
        return cached["kpis"]
    return _get_kpis_live()


def _get_kpis_live() -> dict:
    """Compute KPIs from parsed_* (used when snapshot empty or for refresh)."""
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
    Return tCO2e per GHG scope for the doughnut chart. Uses cached snapshot when available.
    """
    cached = get_dashboard()
    if cached and "emissions_by_scope" in cached:
        return cached["emissions_by_scope"]
    return _get_emissions_by_scope_live()


def _get_emissions_by_scope_live() -> list[dict]:
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
    Return tCO2e per emission source for the horizontal bar chart. Uses cached snapshot when available.
    """
    cached = get_dashboard()
    if cached and "emissions_by_source" in cached:
        return cached["emissions_by_source"]
    return _get_emissions_by_source_live()


def _get_emissions_by_source_live() -> list[dict]:
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
        "id": 0,
        "title": "No Data Found",
        "description": "No sustainability data available to generate recommendations. Ingest documents to populate the database, then run the recommendation engine.",
        "priority": "low",
        "category": "general",
        "potential_saving_tco2e": None,
    },
]


def get_recommendations() -> list[dict]:
    """
    Return recommendations. Uses cached snapshot when available.
    """
    cached = get_dashboard()
    if cached and "recommendations" in cached:
        return cached["recommendations"]
    return _get_recommendations_live()


def _get_recommendations_live() -> list[dict]:
    rows = db.query(
        """
        SELECT r.recommendation_id AS id,
               r.recommendation_text AS description,
               a.activity_type AS category,
               r.criteria, r.saving_kg_co2e, r.score
        FROM recommendations r
        LEFT JOIN activities a ON a.activity_id = r.activity_id
        ORDER BY r.score DESC NULLS LAST
        LIMIT 15
        """
    )
    if rows:
        return [
            {
                "id": row["id"],
                "title": (row.get("criteria") or row.get("category") or "Recommendation").replace("_", " ").title(),
                "description": row["description"],
                "priority": (
                    "high" if row.get("saving_kg_co2e") is not None and float(row["saving_kg_co2e"]) > 50
                    else "medium" if row.get("saving_kg_co2e") is not None and float(row["saving_kg_co2e"]) > 10
                    else "low"
                ),
                "category": row.get("criteria") or row.get("category") or "general",
                "potential_saving_tco2e": round(float(row["saving_kg_co2e"]) / 1000, 4) if row.get("saving_kg_co2e") else None,
            }
            for row in rows
        ]
    return _STATIC_RECOMMENDATIONS
