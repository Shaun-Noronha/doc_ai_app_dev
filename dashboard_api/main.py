"""
main.py – FastAPI dashboard API for SME Sustainability Pulse.

Start:
    cd /path/to/doc_ai_app_dev
    uvicorn dashboard_api.main:app --reload --port 8000

Upload/confirm run in-process via sme_doc_extract_local.service (no separate Doc AI server).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Load .env from repo root so DATABASE_URL is available
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_repo_root))
for _env_path in (_repo_root / ".env", _repo_root / "sme_doc_extract_local" / ".env"):
    if _env_path.exists():
        load_dotenv(_env_path)
        break

from . import queries  # noqa: E402 – needs dotenv loaded first
from . import recommendations as rec_engine  # noqa: E402
from . import vendors as vendors_module  # noqa: E402

try:
    from sme_doc_extract_local.service import handle_upload as _handle_upload, handle_confirm as _handle_confirm
except ImportError:
    _handle_upload = _handle_confirm = None

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


@app.post("/api/upload", summary="Upload document for Doc AI + Gemini extraction")
async def upload(file: UploadFile = File(...)):
    """
    Receive file → Doc AI OCR → classify → Gemini extraction → return review fields.
    Runs in-process via sme_doc_extract_local.service.
    """
    if _handle_upload is None:
        raise HTTPException(
            status_code=503,
            detail="Document upload not available. Install Doc AI dependencies and ensure sme_doc_extract_local is on Python path.",
        )
    contents = await file.read()
    filename = file.filename or "document"
    suffix = Path(filename).suffix.lower() or ".pdf"
    try:
        result = await asyncio.to_thread(_handle_upload, contents, filename, suffix)
        return result
    except RuntimeError as e:
        msg = str(e)
        if "packages not installed" in msg:
            raise HTTPException(status_code=501, detail=msg) from e
        raise HTTPException(status_code=500, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/confirm", summary="Confirm extracted fields and save to DB")
async def confirm(body: dict):
    """
    Save confirmed extraction, run calculations, return updated dashboard.
    Runs in-process via sme_doc_extract_local.service.
    """
    if _handle_confirm is None:
        raise HTTPException(
            status_code=503,
            detail="Document confirm not available. Install Doc AI dependencies and ensure sme_doc_extract_local is on Python path.",
        )
    try:
        doc_id = await asyncio.to_thread(_handle_confirm, body)
        dashboard = queries.get_dashboard_live()
        return {"ok": True, "document_id": doc_id, "dashboard": dashboard}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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


@app.get("/api/documents", summary="Documents that contributed data")
def documents(scope: int | None = None):
    """
    Return documents; optional scope 0 (water), 1, 2, or 3 for scope-specific sources.
    """
    try:
        if scope is not None:
            return queries.get_documents_by_scope(scope)
        return queries.get_documents_all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/scope/{scope}", summary="Scope-specific payload (scopeTotal, bySource, sparkline, documents)")
def scope_payload(scope: int):
    """Scope must be 1, 2, or 3."""
    if scope not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="scope must be 1, 2, or 3")
    try:
        return queries.get_scope_payload(scope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/water", summary="Water view payload (water_usage, sparkline, documents)")
def water():
    try:
        return queries.get_water_payload()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/vendors", summary="All vendors")
def api_vendors():
    try:
        return vendors_module.get_vendors()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/vendors/selected", summary="Selected vendor IDs")
def vendors_selected():
    try:
        return vendors_module.get_selected_vendor_ids()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/vendors/selected", summary="Set selected vendor IDs")
def set_vendors_selected(body: dict):
    """Body: { \"vendor_ids\": string[] }. Returns the saved list of selected ids."""
    try:
        vendor_ids = body.get("vendor_ids") or []
        if not isinstance(vendor_ids, list):
            vendor_ids = []
        vendor_ids = [str(v) for v in vendor_ids]
        vendors_module.set_selected_vendors(vendor_ids)
        return vendors_module.get_selected_vendor_ids()
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
