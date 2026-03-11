"""
recommendations.py – Content-Based Sustainability Recommender System.

A content-based RS that uses the vendor knowledge base + parsed emission
records to generate specific, actionable recommendations.

Pipeline
--------
1. Load vendor profiles and emission records from DB.
2. For each criterion, build candidate recommendations by matching records
   to vendors or comparing vendor profiles via cosine similarity.
3. Score each candidate:  saving × vendor_sustainability / 100.
4. Normalise scores with MinMaxScaler.
5. MMR diversity rerank with cosine similarity to remove near-duplicates.
6. Persist top-N per criterion; refresh dashboard snapshot.

Three criteria
--------------
1. Better Closer Hauler  – match shipping records to closer Logistics vendors.
2. Alternative Material   – within each vendor category, recommend greener
                            vendor over the high-carbon one (cosine similarity
                            on vendor profiles to find the best substitute).
3. Change Shipment Method – recommend switching transport mode for shipping.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics.pairwise import cosine_similarity as cos_sim
from psycopg2.extras import RealDictCursor

from . import db
from . import queries
from .emission_factors import VEHICLE_FUEL_KG, STATIONARY_FUEL_KG

logger = logging.getLogger(__name__)

MODE_FACTORS = {"truck": 0.1693, "rail": 0.0229, "ship": 0.0098, "air": 1.1300}
MODE_FEASIBILITY = {"truck": 0.95, "rail": 0.70, "ship": 0.50, "air": 0.95}

_MIGRATION_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='criteria') THEN
        ALTER TABLE recommendations ADD COLUMN criteria VARCHAR(30);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='current_kg_co2e') THEN
        ALTER TABLE recommendations ADD COLUMN current_kg_co2e NUMERIC(18,6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='recommended_kg_co2e') THEN
        ALTER TABLE recommendations ADD COLUMN recommended_kg_co2e NUMERIC(18,6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='saving_kg_co2e') THEN
        ALTER TABLE recommendations ADD COLUMN saving_kg_co2e NUMERIC(18,6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='score') THEN
        ALTER TABLE recommendations ADD COLUMN score NUMERIC(18,6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='source_parsed_id') THEN
        ALTER TABLE recommendations ADD COLUMN source_parsed_id BIGINT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='recommendations' AND column_name='record_count') THEN
        ALTER TABLE recommendations ADD COLUMN record_count INT DEFAULT 1;
    END IF;
END; $$;
"""

def _load(cur, sql):
    cur.execute(sql)
    return [dict(r) for r in cur.fetchall()]

def _f(d, k, default=0.0):
    return float(d.get(k) or default)

def _group(records, key_fn):
    buckets: dict = {}
    for r in records:
        buckets.setdefault(key_fn(r), []).append(r)
    return list(buckets.values())


# ═════════════════════════════════════════════════════════════════════════════
# CRITERION 1 — Better Closer Hauler
# Match each shipping group to a Logistics vendor that is CLOSER with a
# good sustainability score.  Cosine similarity between the record's
# [distance, weight, emissions] profile and each vendor's profile.
# ═════════════════════════════════════════════════════════════════════════════

def _candidates_closer_hauler(ship_groups, logistics_vendors):
    candidates = []
    for group in ship_groups:
        rep = group[0]
        dist_mi = _f(rep, "distance_miles")
        weight = _f(rep, "weight_tons")
        if dist_mi <= 0 or weight <= 0:
            continue

        mode = (rep.get("transport_mode") or "truck").lower()
        factor = MODE_FACTORS.get(mode, 0.1693)
        current_kg = dist_mi * weight * factor
        n = len(group)

        for v in logistics_vendors:
            v_dist_mi = _f(v, "distance_km_from_sme") * 0.621371
            v_score = _f(v, "sustainability_score")
            v_carbon = _f(v, "carbon_intensity")
            if v_dist_mi >= dist_mi:
                continue

            new_kg = v_dist_mi * weight * factor
            saving = current_kg - new_kg
            if saving <= 0:
                continue

            rec_vec = np.array([[dist_mi, weight, current_kg]])
            ven_vec = np.array([[v_dist_mi, weight, v_carbon]])
            sim = float(cos_sim(rec_vec, ven_vec)[0, 0])

            pct = (dist_mi - v_dist_mi) / dist_mi * 100
            candidates.append({
                "criteria": "better_closer_hauler",
                "activity_id": rep.get("activity_id"),
                "source_parsed_id": rep["parsed_id"],
                "current_kg": round(current_kg, 4),
                "recommended_kg": round(new_kg, 4),
                "saving_kg": round(saving, 4),
                "total_saving_kg": round(saving * n, 4),
                "raw_score": saving * n * (v_score / 100),
                "record_count": n,
                "similarity": round(sim, 4),
                "feature_vec": [dist_mi, weight, saving, v_score],
                "text": (
                    f"Switch {n} shipment{'s' if n > 1 else ''} "
                    f"({dist_mi:.0f} mi, {weight:.1f} tons, {mode}) "
                    f"to \"{v['vendor_name']}\" — only "
                    f"{_f(v, 'distance_km_from_sme'):.0f} km away, "
                    f"sustainability {int(v_score)}/100. "
                    f"{pct:.0f}% closer, saves {saving:.1f} kg CO₂e/shipment "
                    f"({saving * n:.1f} kg total)."
                ),
            })
    return candidates


# ═════════════════════════════════════════════════════════════════════════════
# CRITERION 2 — Alternative Material
# Within each vendor category, use cosine similarity on vendor profiles
# [1/carbon_intensity, sustainability_score, 1/distance] to find the
# greenest substitute for the least-sustainable vendor.
# ═════════════════════════════════════════════════════════════════════════════

def _candidates_alt_material(vendors, fallback_activity_id):
    by_cat: dict[str, list[dict]] = {}
    for v in vendors:
        cat = v.get("category") or "Other"
        if cat == "Logistics":
            continue
        by_cat.setdefault(cat, []).append(v)

    candidates = []
    for cat, vs in by_cat.items():
        if len(vs) < 2:
            continue

        profiles = []
        for v in vs:
            ci = max(_f(v, "carbon_intensity"), 0.01)
            ss = _f(v, "sustainability_score")
            dk = max(_f(v, "distance_km_from_sme"), 1.0)
            profiles.append([1.0 / ci, ss, 1.0 / dk])
        X = np.array(profiles)

        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        sim_matrix = cos_sim(X / norms)

        worst_idx = int(np.argmax([_f(v, "carbon_intensity") for v in vs]))
        worst = vs[worst_idx]
        worst_ci = _f(worst, "carbon_intensity")

        sims_to_worst = sim_matrix[worst_idx]
        best_idx = None
        best_combined = -1.0
        for j, v in enumerate(vs):
            if j == worst_idx:
                continue
            v_ci = _f(v, "carbon_intensity")
            if v_ci >= worst_ci:
                continue
            saving_pct = (worst_ci - v_ci) / worst_ci
            combined = saving_pct * 0.5 + (_f(v, "sustainability_score") / 100) * 0.3 + sims_to_worst[j] * 0.2
            if combined > best_combined:
                best_combined = combined
                best_idx = j

        if best_idx is None:
            continue

        best = vs[best_idx]
        best_ci = _f(best, "carbon_intensity")
        saving_per_unit = worst_ci - best_ci
        pct_reduction = saving_per_unit / worst_ci * 100
        similarity = float(sims_to_worst[best_idx])

        candidates.append({
            "criteria": "alternative_material",
            "activity_id": fallback_activity_id,
            "source_parsed_id": None,
            "current_kg": round(worst_ci, 4),
            "recommended_kg": round(best_ci, 4),
            "saving_kg": round(saving_per_unit, 4),
            "total_saving_kg": round(saving_per_unit, 4),
            "raw_score": saving_per_unit * (_f(best, "sustainability_score") / 100),
            "record_count": 1,
            "similarity": round(similarity, 4),
            "feature_vec": [worst_ci, best_ci, saving_per_unit, _f(best, "sustainability_score")],
            "text": (
                f"{cat}: switch from \"{worst['vendor_name']}\" "
                f"({worst_ci:.1f} kg CO₂e/unit, score {int(_f(worst, 'sustainability_score'))}) "
                f"to \"{best['vendor_name']}\" "
                f"({best_ci:.1f} kg CO₂e/unit, score {int(_f(best, 'sustainability_score'))}). "
                f"{pct_reduction:.0f}% lower carbon intensity, "
                f"{_f(best, 'distance_km_from_sme'):.0f} km away "
                f"(vs {_f(worst, 'distance_km_from_sme'):.0f} km). "
                f"Similarity: {similarity:.0%}."
            ),
        })

    return candidates


# ═════════════════════════════════════════════════════════════════════════════
# CRITERION 3 — Change Shipment Method
# For each shipping group, compute emissions under every viable transport
# mode and recommend the best switch.
# ═════════════════════════════════════════════════════════════════════════════

def _candidates_change_mode(ship_groups):
    candidates = []
    for group in ship_groups:
        rep = group[0]
        dist = _f(rep, "distance_miles")
        weight = _f(rep, "weight_tons")
        if dist <= 0 or weight <= 0:
            continue

        tm = dist * weight
        cur_mode = (rep.get("transport_mode") or "truck").lower()
        cur_kg = tm * MODE_FACTORS.get(cur_mode, 0.1693)
        n = len(group)

        best_mode, best_sc, best_new = None, 0.0, cur_kg
        for mode, fac in MODE_FACTORS.items():
            if mode == cur_mode:
                continue
            if mode == "rail" and dist < 100:
                continue
            if mode == "ship" and dist < 200:
                continue
            nkg = tm * fac
            s = cur_kg - nkg
            if s <= 0:
                continue
            sc = s * MODE_FEASIBILITY.get(mode, 0.5)
            if sc > best_sc:
                best_mode, best_sc, best_new = mode, sc, nkg

        if not best_mode:
            continue

        saving = cur_kg - best_new
        pct = saving / cur_kg * 100
        candidates.append({
            "criteria": "change_shipment_method",
            "activity_id": rep.get("activity_id"),
            "source_parsed_id": rep["parsed_id"],
            "current_kg": round(cur_kg, 4),
            "recommended_kg": round(best_new, 4),
            "saving_kg": round(saving, 4),
            "total_saving_kg": round(saving * n, 4),
            "raw_score": saving * n * MODE_FEASIBILITY.get(best_mode, 0.5),
            "record_count": n,
            "similarity": 0.0,
            "feature_vec": [dist, weight, saving, MODE_FEASIBILITY.get(best_mode, 0.5) * 100],
            "text": (
                f"{n} shipment{'s' if n > 1 else ''}: "
                f"{dist:.0f} mi × {weight:.1f} tons via {cur_mode} "
                f"({cur_kg:.1f} kg CO₂e each). "
                f"Switch to {best_mode} — cuts {pct:.0f}%, "
                f"saves {saving:.1f} kg/shipment, "
                f"{saving * n:.1f} kg total."
            ),
        })
    return candidates


# ═════════════════════════════════════════════════════════════════════════════
# CRITERION 4 — Reduce Fuel Emissions
# For vehicle fuel records using diesel, recommend switching to gasoline.
# For stationary fuel using heating_oil, recommend switching to propane.
# Match against Energy vendors for supplier scoring via cosine similarity.
# ═════════════════════════════════════════════════════════════════════════════

_VEHICLE_SWITCH: dict[str, tuple[str, str]] = {
    "diesel": ("gasoline", "gallon"),
}

_STATIONARY_SWITCH: dict[str, tuple[str, str]] = {
    "heating_oil": ("propane", "gallon"),
}


def _candidates_reduce_fuel(veh_groups, stat_groups, energy_vendors):
    candidates = []

    for group in veh_groups:
        rep = group[0]
        fuel = (rep.get("fuel_type") or "").lower()
        unit = (rep.get("unit") or "gallon").lower()
        qty = _f(rep, "quantity")
        if qty <= 0 or fuel not in _VEHICLE_SWITCH:
            continue

        alt_fuel, alt_unit = _VEHICLE_SWITCH[fuel]
        cur_factor = VEHICLE_FUEL_KG.get(fuel, {}).get(unit, 0)
        alt_factor = VEHICLE_FUEL_KG.get(alt_fuel, {}).get(alt_unit, 0)
        if cur_factor <= alt_factor:
            continue

        current_kg = qty * cur_factor
        new_kg = qty * alt_factor
        saving = current_kg - new_kg
        n = len(group)
        pct = saving / current_kg * 100

        best_v, best_sc = None, 0.0
        for v in energy_vendors:
            v_score = _f(v, "sustainability_score")
            rec_vec = np.array([[qty, current_kg, saving]])
            ven_vec = np.array([[1.0 / max(_f(v, "carbon_intensity"), 0.01), v_score,
                                 1.0 / max(_f(v, "distance_km_from_sme"), 1)]])
            sim = float(cos_sim(rec_vec, ven_vec)[0, 0])
            sc = saving * n * (v_score / 100) * (1 + sim) / 2
            if sc > best_sc:
                best_v, best_sc = v, sc

        v_sus = _f(best_v, "sustainability_score") if best_v else 50
        vendor_note = ""
        if best_v:
            vendor_note = (
                f" Consider \"{best_v['vendor_name']}\" "
                f"(sustainability {int(v_sus)}/100) as energy supplier."
            )

        candidates.append({
            "criteria": "reduce_fuel_emissions",
            "activity_id": rep.get("activity_id"),
            "source_parsed_id": rep["parsed_id"],
            "current_kg": round(current_kg, 4),
            "recommended_kg": round(new_kg, 4),
            "saving_kg": round(saving, 4),
            "total_saving_kg": round(saving * n, 4),
            "raw_score": best_sc if best_sc > 0 else saving * n * 0.5,
            "record_count": n,
            "similarity": 0.0,
            "feature_vec": [qty, current_kg, saving, v_sus],
            "text": (
                f"{n} record{'s' if n > 1 else ''}: {qty:.1f} {unit} {fuel} "
                f"({current_kg:.1f} kg CO₂e each). "
                f"Switch to {alt_fuel} -- cuts {pct:.0f}%, "
                f"saves {saving:.1f} kg/record, "
                f"{saving * n:.1f} kg total.{vendor_note}"
            ),
        })

    for group in stat_groups:
        rep = group[0]
        fuel = (rep.get("fuel_type") or "").lower()
        unit = (rep.get("unit") or "gallon").lower()
        qty = _f(rep, "quantity")
        if qty <= 0 or fuel not in _STATIONARY_SWITCH:
            continue

        alt_fuel, alt_unit = _STATIONARY_SWITCH[fuel]
        cur_factor = STATIONARY_FUEL_KG.get(fuel, {}).get(unit, 0)
        alt_factor = STATIONARY_FUEL_KG.get(alt_fuel, {}).get(alt_unit, 0)
        if cur_factor <= alt_factor:
            continue

        current_kg = qty * cur_factor
        new_kg = qty * alt_factor
        saving = current_kg - new_kg
        n = len(group)
        pct = saving / current_kg * 100

        candidates.append({
            "criteria": "reduce_fuel_emissions",
            "activity_id": rep.get("activity_id"),
            "source_parsed_id": rep["parsed_id"],
            "current_kg": round(current_kg, 4),
            "recommended_kg": round(new_kg, 4),
            "saving_kg": round(saving, 4),
            "total_saving_kg": round(saving * n, 4),
            "raw_score": saving * n * 0.7,
            "record_count": n,
            "similarity": 0.0,
            "feature_vec": [qty, current_kg, saving, 70],
            "text": (
                f"{n} record{'s' if n > 1 else ''}: {qty:.1f} {unit} {fuel} "
                f"({current_kg:.1f} kg CO₂e each). "
                f"Switch to {alt_fuel} -- cuts {pct:.0f}%, "
                f"saves {saving:.1f} kg/record, "
                f"{saving * n:.1f} kg total."
            ),
        })

    return candidates


# ═════════════════════════════════════════════════════════════════════════════
# CRITERION 5 — Green Electricity Provider
# Match total electricity consumption against Energy vendors whose carbon
# intensity is below the US average grid factor.  Cosine similarity on
# [kWh, current_emissions, grid_factor] vs [1/vendor_ci, score, 1/distance].
# ═════════════════════════════════════════════════════════════════════════════

_GRID_KG_PER_KWH = 0.3862


def _candidates_green_electricity(elec_records, energy_vendors):
    candidates = []
    if not elec_records or not energy_vendors:
        return candidates

    total_kwh = sum(_f(r, "kwh") for r in elec_records)
    if total_kwh <= 0:
        return candidates

    current_kg = total_kwh * _GRID_KG_PER_KWH
    n = len(elec_records)

    rep_aid = None
    rep_pid = elec_records[0]["parsed_id"]
    for r in elec_records:
        if r.get("activity_id"):
            rep_aid = r["activity_id"]
            break

    if not rep_aid:
        return candidates

    for v in energy_vendors:
        v_ci = _f(v, "carbon_intensity")
        v_score = _f(v, "sustainability_score")
        v_name = v["vendor_name"]

        if v_ci >= _GRID_KG_PER_KWH:
            continue

        new_kg = total_kwh * v_ci
        saving = current_kg - new_kg
        if saving <= 0:
            continue

        pct = saving / current_kg * 100

        rec_vec = np.array([[total_kwh, current_kg, _GRID_KG_PER_KWH]])
        ven_vec = np.array([[1.0 / max(v_ci, 0.001), v_score,
                             1.0 / max(_f(v, "distance_km_from_sme"), 1)]])
        sim = float(cos_sim(rec_vec, ven_vec)[0, 0])

        candidates.append({
            "criteria": "green_electricity",
            "activity_id": rep_aid,
            "source_parsed_id": rep_pid,
            "current_kg": round(current_kg, 4),
            "recommended_kg": round(new_kg, 4),
            "saving_kg": round(saving, 4),
            "total_saving_kg": round(saving, 4),
            "raw_score": saving * (v_score / 100) * (1 + sim) / 2,
            "record_count": n,
            "similarity": round(sim, 4),
            "feature_vec": [total_kwh, current_kg, saving, v_score],
            "text": (
                f"Switch {total_kwh:,.0f} kWh ({n} bill{'s' if n > 1 else ''}) "
                f"from grid ({_GRID_KG_PER_KWH} kg/kWh) to \"{v_name}\" "
                f"({v_ci:.4f} kg/kWh, sustainability {int(v_score)}/100). "
                f"Saves {saving:.1f} kg CO₂e ({pct:.0f}% reduction)."
            ),
        })

    return candidates


# ─── Normalise + MMR ─────────────────────────────────────────────────────────

def _normalise(cands):
    if len(cands) < 2:
        for c in cands:
            c["score"] = 1.0
        return
    raw = np.array([c["raw_score"] for c in cands]).reshape(-1, 1)
    normed = MinMaxScaler().fit_transform(raw).flatten()
    for i, c in enumerate(cands):
        c["score"] = round(float(normed[i]), 6)


def _mmr_rerank(cands, lam=0.7, threshold=0.93):
    if len(cands) <= 1:
        return list(cands)
    vecs = np.array([c["feature_vec"] for c in cands])
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = cos_sim(vecs / norms)
    scores = np.array([c["score"] for c in cands])

    sel = [int(np.argmax(scores))]
    rem = set(range(len(cands))) - set(sel)
    while rem:
        bi, bm = -1, -np.inf
        for i in rem:
            ms = max(sim[i, j] for j in sel)
            m = lam * scores[i] - (1 - lam) * ms
            if m > bm:
                bi, bm = i, m
        if bi < 0:
            break
        if max(sim[bi, j] for j in sel) >= threshold:
            rem.discard(bi)
            continue
        sel.append(bi)
        rem.discard(bi)
    return [cands[i] for i in sel]


# ─── Orchestrator ────────────────────────────────────────────────────────────

def generate(top_n: int = 3) -> dict[str, Any]:
    conn = db.get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_MIGRATION_SQL)
            conn.commit()

            vendors = _load(cur, "SELECT * FROM vendors ORDER BY sustainability_score DESC")
            shipping = _load(cur, """
                SELECT ps.parsed_id, ps.document_id, ps.weight_tons,
                       ps.distance_miles, ps.transport_mode,
                       a.activity_id, e.emissions_kg_co2e
                FROM parsed_shipping ps
                LEFT JOIN activities a ON a.parsed_table='parsed_shipping' AND a.parsed_id=ps.parsed_id
                LEFT JOIN emissions e ON e.activity_id=a.activity_id
            """)

            vehicle_fuel = _load(cur, """
                SELECT pv.parsed_id, pv.document_id, pv.fuel_type,
                       pv.quantity, pv.unit,
                       a.activity_id, e.emissions_kg_co2e
                FROM parsed_vehicle_fuel pv
                LEFT JOIN activities a ON a.parsed_table='parsed_vehicle_fuel'
                    AND a.parsed_id=pv.parsed_id
                LEFT JOIN emissions e ON e.activity_id=a.activity_id
            """)

            stationary_fuel = _load(cur, """
                SELECT psf.parsed_id, psf.document_id, psf.fuel_type,
                       psf.quantity, psf.unit,
                       a.activity_id, e.emissions_kg_co2e
                FROM parsed_stationary_fuel psf
                LEFT JOIN activities a ON a.parsed_table='parsed_stationary_fuel'
                    AND a.parsed_id=psf.parsed_id
                LEFT JOIN emissions e ON e.activity_id=a.activity_id
            """)

            electricity = _load(cur, """
                SELECT pe.parsed_id, pe.document_id, pe.kwh,
                       pe.unit, pe.location,
                       a.activity_id, e.emissions_kg_co2e
                FROM parsed_electricity pe
                LEFT JOIN activities a ON a.parsed_table='parsed_electricity'
                    AND a.parsed_id=pe.parsed_id
                LEFT JOIN emissions e ON e.activity_id=a.activity_id
            """)

            fallback_aid = None
            row = _load(cur, "SELECT activity_id FROM activities LIMIT 1")
            if row:
                fallback_aid = row[0]["activity_id"]

        logistics_v = [v for v in vendors if v["category"] == "Logistics"]
        energy_v = [v for v in vendors if v.get("category") in ("Energy", "Energy Provider")]

        ship_groups = _group(shipping, lambda r: (
            round(_f(r, "distance_miles")),
            round(_f(r, "weight_tons"), 1),
            (r.get("transport_mode") or "truck").lower(),
        ))

        veh_groups = _group(vehicle_fuel, lambda r: (
            (r.get("fuel_type") or "").lower(),
            (r.get("unit") or "gallon").lower(),
            round(_f(r, "quantity"), 1),
        ))

        stat_groups = _group(stationary_fuel, lambda r: (
            (r.get("fuel_type") or "").lower(),
            (r.get("unit") or "therm").lower(),
            round(_f(r, "quantity"), 1),
        ))

        c1 = _candidates_closer_hauler(ship_groups, logistics_v)
        c2 = _candidates_alt_material(vendors, fallback_aid)
        c3 = _candidates_change_mode(ship_groups)
        c4 = _candidates_reduce_fuel(veh_groups, stat_groups, energy_v)
        c5 = _candidates_green_electricity(electricity, energy_v)

        all_cands = c1 + c2 + c3 + c4 + c5
        logger.info(
            "Candidates: %d hauler, %d material, %d mode, %d fuel, %d electricity = %d total",
            len(c1), len(c2), len(c3), len(c4), len(c5), len(all_cands),
        )

        _normalise(all_cands)

        # Apply MMR per-criterion to guarantee all 3 are represented,
        # while still removing near-duplicates within the same type.
        by_crit: dict[str, list[dict]] = {}
        for c in all_cands:
            by_crit.setdefault(c["criteria"], []).append(c)

        selected: list[dict] = []
        for crit, cands in by_crit.items():
            cands.sort(key=lambda c: c["score"], reverse=True)
            diverse_crit = _mmr_rerank(cands, lam=0.7, threshold=0.93)
            selected.extend(diverse_crit[:top_n])

        with conn.cursor() as cur:
            cur.execute("DELETE FROM recommendations")
            for rec in selected:
                aid = rec.get("activity_id")
                if not aid:
                    continue
                cur.execute(
                    """INSERT INTO recommendations
                        (activity_id, recommendation_text, criteria,
                         current_kg_co2e, recommended_kg_co2e, saving_kg_co2e,
                         score, source_parsed_id, record_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (aid, rec["text"], rec["criteria"],
                     rec["current_kg"], rec["recommended_kg"],
                     rec["saving_kg"], rec["score"],
                     rec["source_parsed_id"], rec["record_count"]),
                )
            conn.commit()

        total_saving = sum(r["total_saving_kg"] for r in selected)
        try:
            queries.refresh_snapshot()
        except Exception as exc:
            logger.warning("Could not refresh snapshot: %s", exc)

        return {
            "vendors_used": len(vendors),
            "shipping_groups": len(ship_groups),
            "candidates": {"hauler": len(c1), "material": len(c2), "mode": len(c3), "fuel": len(c4), "electricity": len(c5)},
            "after_diversity": len(selected),
            "saved": len(selected),
            "total_saving_kg": round(total_saving, 2),
            "recommendations": [
                {
                    "criteria": r["criteria"],
                    "records_affected": r["record_count"],
                    "saving_kg": r["saving_kg"],
                    "total_saving_kg": r["total_saving_kg"],
                    "score": r["score"],
                    "similarity": r.get("similarity"),
                    "text": r["text"],
                }
                for r in selected
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch(criteria: str | None = None) -> list[dict]:
    sql = """
        SELECT r.recommendation_id, r.activity_id, r.recommendation_text,
               r.criteria, r.current_kg_co2e, r.recommended_kg_co2e,
               r.saving_kg_co2e, r.score, r.source_parsed_id,
               r.record_count, r.created_at, a.activity_type, a.scope
        FROM recommendations r
        LEFT JOIN activities a ON a.activity_id = r.activity_id
    """
    params: list[Any] = []
    if criteria:
        sql += " WHERE r.criteria = %s"
        params.append(criteria)
    sql += " ORDER BY r.score DESC NULLS LAST"
    rows = db.query(sql, tuple(params))
    return [
        {
            "id": r["recommendation_id"],
            "criteria": r.get("criteria"),
            "title": (r.get("criteria") or "recommendation").replace("_", " ").title(),
            "description": r["recommendation_text"],
            "current_kg_co2e": float(r["current_kg_co2e"]) if r.get("current_kg_co2e") is not None else None,
            "recommended_kg_co2e": float(r["recommended_kg_co2e"]) if r.get("recommended_kg_co2e") is not None else None,
            "saving_kg_co2e": float(r["saving_kg_co2e"]) if r.get("saving_kg_co2e") is not None else None,
            "score": float(r["score"]) if r.get("score") is not None else None,
            "records_affected": r.get("record_count") or 1,
            "priority": (
                "high" if r.get("saving_kg_co2e") is not None and float(r["saving_kg_co2e"]) > 3
                else "medium" if r.get("saving_kg_co2e") is not None and float(r["saving_kg_co2e"]) > 1
                else "low"
            ),
            "category": r.get("criteria") or r.get("activity_type") or "general",
        }
        for r in rows
    ]
