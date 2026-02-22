"""
main.py – FastAPI dashboard API for SME Sustainability Pulse.

Start:
    cd /path/to/doc_ai_app_dev
    uvicorn dashboard_api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load .env from repo root so DATABASE_URL is available
_repo_root = Path(__file__).resolve().parent.parent
for _env_path in (_repo_root / ".env", _repo_root / "sme_doc_extract_local" / ".env"):
    if _env_path.exists():
        load_dotenv(_env_path)
        break

from . import queries  # noqa: E402 – needs dotenv loaded first
from . import recommendations as rec_engine  # noqa: E402

app = FastAPI(
    title="SME Sustainability Pulse – Dashboard API",
    version="1.0.0",
    description="Aggregated KPIs and chart data derived from parsed document tables.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/dashboard", summary="Full dashboard payload (live)")
def dashboard():
    """
    Returns kpis, emissions_by_scope, emissions_by_source, recommendations.
    Always built from current DB so the dashboard reflects latest data (e.g. after seed).
    """
    try:
        return queries.get_dashboard_live()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/refresh", summary="Rebuild dashboard snapshot")
def refresh():
    """
    Recompute dashboard from parsed_* and write to dashboard_snapshot.
    Call after ingest or on a schedule.
    """
    try:
        queries.refresh_snapshot()
        return {"status": "ok", "message": "Dashboard snapshot refreshed."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/kpis", summary="Top-level KPI metrics")
def kpis():
    """
    Returns total_emissions_tco2e, energy_kwh, water_m3,
    waste_diversion_rate (0-100), and a monthly emissions sparkline.
    """
    try:
        return queries.get_kpis()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/emissions-by-scope", summary="GHG emissions split by scope")
def emissions_by_scope():
    """
    Returns [{scope, label, tco2e}] for Scopes 1, 2, 3.
    Used by the doughnut chart.
    """
    try:
        return queries.get_emissions_by_scope()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/emissions-by-source", summary="GHG emissions split by source")
def emissions_by_source():
    """
    Returns [{source, scope, tco2e}] sorted by tco2e descending.
    Used by the horizontal bar chart.
    """
    try:
        return queries.get_emissions_by_source()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/scope/{scope}", summary="Lightweight payload for Scope 1, 2, or 3 view")
def get_scope(scope: int):
    """Returns scopeTotal, bySource, sparkline, documents for the given scope (1, 2, or 3)."""
    if scope not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="scope must be 1, 2, or 3")
    try:
        return queries.get_scope_payload(scope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/water", summary="Lightweight payload for Water view")
def get_water():
    """Returns water_usage, sparkline, documents. Fast, 3 queries only."""
    try:
        return queries.get_water_payload()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/documents", summary="Documents (optionally by scope)")
def get_documents(scope: int | None = None):
    """
    Return documents that contributed data. If scope is 1, 2, or 3,
    return only documents for that scope (Scope 1: fuel; 2: electricity; 3: shipping/waste).
    """
    try:
        if scope is not None and scope in (0, 1, 2, 3):
            return queries.get_documents_by_scope(scope)
        return queries.get_documents_all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/recommendations", summary="AI improvement recommendations")
def api_recommendations():
    """
    Returns up to 10 recommendations from DB; falls back to 2 static items
    when the recommendations table is empty.
    """
    try:
        return queries.get_recommendations()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/recommendations/generate", summary="Run the recommendation engine")
def generate_recommendations():
    """
    Evaluate every record against the 3 criteria (Better Closer Hauler,
    Alternative Material, Change Shipment Method), rank by utility score,
    and persist the top recommendations.
    """
    try:
        return rec_engine.generate()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/recommendations", summary="Fetch scored recommendations")
def get_recommendations(criteria: str | None = None):
    """
    Return persisted recommendations, optionally filtered by criteria
    (better_closer_hauler, alternative_material, change_shipment_method).
    """
    try:
        return rec_engine.fetch(criteria=criteria)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok"}
