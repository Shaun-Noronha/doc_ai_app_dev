"""
app.py – Flask web server for the SME Sustainability Pulse dashboard.

Serves the compiled React dashboard as static files and provides JSON
API endpoints consumed by the frontend.

Routes
------
GET  /                 → Serve compiled React build (index.html)
GET  /api/dashboard    → Full dashboard payload (kpis, charts, recommendations)
POST /api/refresh      → Re-run calculations, return 200
POST /api/upload       → Receive file, run Doc AI + Gemini, return review fields
POST /api/confirm      → Save confirmed extraction, run calcs, return dashboard

Usage
-----
    python app.py                        # dev server on port 8000
    PORT=9000 python app.py              # custom port
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

# Make "from src.*" importable when running from sme_doc_extract_local/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

_here = Path(__file__).resolve().parent
for _env in (_here / ".env", _here.parent / ".env"):
    if _env.exists():
        load_dotenv(_env)
        break

from flask import Flask, jsonify, request, send_from_directory

from src.config import get_config
from src.db import get_connection, insert_document, insert_category, resolve_utility_subtype
from src.calculations import run_all_calculations
from src.constants import (
    DOC_TYPE_UTILITY_BILL,
    DOC_TYPE_INVOICE,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_DELIVERY_RECEIPT,
    DOC_TYPE_LOGISTICS,
)

# NOTE: google-cloud-documentai, gemini extractors, and classify are imported
# lazily inside api_upload() so the server starts even without those packages.

# ── Static files: compiled React build ──────────────────────────────────────
_DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"

app = Flask(
    __name__,
    static_folder=str(_DIST) if _DIST.exists() else None,
    static_url_path="",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


def _get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in the environment.")
    return get_connection(url)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_kpis(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(emissions_metric_tons), 0) FROM emissions")
        total_tco2e = float(cur.fetchone()[0])

        cur.execute("SELECT COALESCE(SUM(kwh), 0) FROM parsed_electricity")
        total_kwh = float(cur.fetchone()[0])

        cur.execute("SELECT COALESCE(SUM(total_water_volume), 0) FROM water_metrics")
        total_water_gallons = float(cur.fetchone()[0])
        total_water_m3 = round(total_water_gallons / 264.172, 2)

        cur.execute(
            "SELECT COALESCE(diversion_rate, 0) FROM waste_metrics "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        diversion_pct = float(row[0]) * 100 if row else 0.0

        # Sparkline: up to 6 distinct periods ordered chronologically
        cur.execute(
            """
            SELECT TO_CHAR(a.period_start, 'Mon YYYY') AS period,
                   SUM(e.emissions_metric_tons) AS tco2e
            FROM activities a
            JOIN emissions e ON e.activity_id = a.activity_id
            WHERE a.period_start IS NOT NULL
            GROUP BY a.period_start
            ORDER BY a.period_start DESC
            LIMIT 6
            """
        )
        sparkline = [
            {"period": r[0], "tco2e": round(float(r[1]), 4)}
            for r in reversed(cur.fetchall())
        ]

    return {
        "total_emissions_tco2e": round(total_tco2e, 4),
        "energy_kwh": round(total_kwh, 2),
        "water_m3": total_water_m3,
        "waste_diversion_rate": round(diversion_pct, 1),
        "sparkline": sparkline,
    }


def _fetch_by_scope(conn) -> list:
    scope_labels = {1: "Scope 1", 2: "Scope 2", 3: "Scope 3"}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.scope, COALESCE(SUM(e.emissions_metric_tons), 0)
            FROM activities a
            JOIN emissions e ON e.activity_id = a.activity_id
            WHERE a.scope IS NOT NULL
            GROUP BY a.scope
            ORDER BY a.scope
            """
        )
        return [
            {
                "scope": f"scope{r[0]}",
                "label": scope_labels.get(r[0], f"Scope {r[0]}"),
                "tco2e": round(float(r[1]), 4),
            }
            for r in cur.fetchall()
        ]


def _fetch_by_source(conn) -> list:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.activity_type, a.scope, COALESCE(SUM(e.emissions_metric_tons), 0)
            FROM activities a
            JOIN emissions e ON e.activity_id = a.activity_id
            GROUP BY a.activity_type, a.scope
            ORDER BY 3 DESC
            """
        )
        return [
            {
                "source": r[0].replace("_", " ").title(),
                "scope": r[1] or 0,
                "tco2e": round(float(r[2]), 4),
            }
            for r in cur.fetchall()
        ]


def _fetch_recommendations(conn) -> list:
    """Generate up to 3 actionable recommendations from live DB data + vendors."""
    recs: list[dict] = []

    with conn.cursor() as cur:
        # 1. Highest-emission scope → reduce it
        cur.execute(
            """
            SELECT a.scope, COALESCE(SUM(e.emissions_metric_tons), 0) AS total
            FROM activities a
            JOIN emissions e ON e.activity_id = a.activity_id
            WHERE a.scope IS NOT NULL
            GROUP BY a.scope
            ORDER BY total DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            scope, val = int(row[0]), float(row[1])
            scope_desc = {
                1: "direct fuel combustion (vehicles + stationary equipment)",
                2: "purchased electricity",
                3: "shipping & waste disposal",
            }
            recs.append({
                "id": 1,
                "title": f"Reduce Scope {scope} emissions",
                "description": (
                    f"Your largest emission source is {scope_desc.get(scope, f'Scope {scope}')} "
                    f"at {val:.2f} tCO₂e. A 15% reduction here would save "
                    f"{val * 0.15:.2f} tCO₂e."
                ),
                "priority": "high",
                "category": f"Scope {scope}",
                "potential_saving_tco2e": round(val * 0.15, 3),
            })

        # 2. Best vendor by sustainability score
        cur.execute(
            """
            SELECT category, vendor_name, carbon_intensity, sustainability_score
            FROM vendors
            ORDER BY sustainability_score DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            cat, name, ci, score = row
            recs.append({
                "id": 2,
                "title": f"Preferred supplier: {name}",
                "description": (
                    f"{name} ({cat}) scores {score}/100 on sustainability with a carbon "
                    f"intensity of {ci} kg CO₂e/unit. Consider them as your primary "
                    f"{cat.lower()} supplier."
                ),
                "priority": "medium",
                "category": cat,
                "potential_saving_tco2e": None,
            })

        # 3. Renewable electricity tip
        cur.execute("SELECT COALESCE(SUM(kwh), 0) FROM parsed_electricity")
        kwh = float(cur.fetchone()[0])
        if kwh > 0:
            saving = round(kwh * 0.000233, 3)  # avg grid → near-zero renewable
            recs.append({
                "id": 3,
                "title": "Switch to renewable electricity",
                "description": (
                    f"You consumed {kwh:,.0f} kWh. Switching to a renewable tariff "
                    f"(e.g. SunGrid Energy, score 92/100) could eliminate up to 90% "
                    f"of your Scope 2 emissions ({saving} tCO₂e saved)."
                ),
                "priority": "medium" if kwh < 5_000 else "high",
                "category": "Energy",
                "potential_saving_tco2e": saving,
            })

    return recs


def _build_dashboard_payload(conn) -> dict:
    return {
        "kpis": _fetch_kpis(conn),
        "emissions_by_scope": _fetch_by_scope(conn),
        "emissions_by_source": _fetch_by_source(conn),
        "recommendations": _fetch_recommendations(conn),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Upload helpers – per-doc-type review fields
# ─────────────────────────────────────────────────────────────────────────────

def _utility_review_fields(extraction: dict, subtype: str) -> list[dict]:
    fields: list[dict] = [
        {"key": "utility_type",          "label": "Utility Type",      "value": subtype,                                   "editable": False},
        {"key": "location",              "label": "Location",          "value": extraction.get("location"),                "editable": False},
        {"key": "billing_period_start",  "label": "Period Start",      "value": extraction.get("billing_period_start"),    "editable": False},
        {"key": "billing_period_end",    "label": "Period End",        "value": extraction.get("billing_period_end"),      "editable": False},
    ]
    if subtype == "electricity":
        fields.append({"key": "electricity_kwh",     "label": "Electricity (kWh)",  "value": extraction.get("electricity_kwh"),     "editable": True})
    elif subtype == "gas":
        fields.append({"key": "natural_gas_therms",  "label": "Gas (therms)",       "value": extraction.get("natural_gas_therms"),  "editable": True})
    elif subtype == "water":
        fields.append({"key": "water_volume",        "label": "Water Volume",       "value": extraction.get("water_volume"),        "editable": True})
        fields.append({"key": "water_unit",          "label": "Unit",               "value": extraction.get("water_unit") or "gallon", "editable": False})
    return fields


def _logistics_review_fields(extraction: dict) -> list[dict]:
    origin = extraction.get("origin") or {}
    dest   = extraction.get("destination") or {}
    origin_str = ", ".join(filter(None, [origin.get("city"), origin.get("state"), origin.get("country")]))
    dest_str   = ", ".join(filter(None, [dest.get("city"),   dest.get("state"),   dest.get("country")]))
    return [
        {"key": "shipment_id",  "label": "Shipment ID",      "value": extraction.get("shipment_id"),  "editable": False},
        {"key": "carrier",      "label": "Carrier",          "value": extraction.get("carrier"),      "editable": False},
        {"key": "mode",         "label": "Transport Mode",   "value": extraction.get("mode"),         "editable": False},
        {"key": "date",         "label": "Shipment Date",    "value": extraction.get("date"),         "editable": False},
        {"key": "origin",       "label": "Origin",           "value": origin_str or None,             "editable": False},
        {"key": "destination",  "label": "Destination",      "value": dest_str or None,               "editable": False},
        {"key": "weight_kg",    "label": "Weight (kg) ★",   "value": extraction.get("weight_kg"),    "editable": True},
        {"key": "distance_km",  "label": "Distance (km) ★", "value": extraction.get("distance_km"),  "editable": True},
        {"key": "packages_count","label": "Packages",        "value": extraction.get("packages_count"), "editable": False},
    ]


def _invoice_review_fields(extraction: dict) -> list[dict]:
    return [
        {"key": "vendor_name",    "label": "Vendor",          "value": extraction.get("vendor_name"),    "editable": False},
        {"key": "invoice_number", "label": "Invoice No.",     "value": extraction.get("invoice_number"), "editable": False},
        {"key": "invoice_date",   "label": "Invoice Date",    "value": extraction.get("invoice_date"),   "editable": False},
        {"key": "due_date",       "label": "Due Date",        "value": extraction.get("due_date"),       "editable": False},
        {"key": "subtotal",       "label": "Subtotal",        "value": extraction.get("subtotal"),       "editable": False},
        {"key": "tax",            "label": "Tax",             "value": extraction.get("tax"),            "editable": False},
        {"key": "total",          "label": "Total (★)",       "value": extraction.get("total"),          "editable": True},
        {"key": "currency",       "label": "Currency",        "value": extraction.get("currency"),       "editable": False},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Confirm helper – rebuild insert payload from review form values
# ─────────────────────────────────────────────────────────────────────────────

_NUMERIC_KEYS = {
    "electricity_kwh", "natural_gas_therms", "water_volume",
    "weight_kg", "distance_km", "total", "subtotal", "tax",
}


def _build_confirm_payload(doc_type: str, fields: dict[str, str], filename: str) -> dict:
    extraction: dict[str, Any] = {}
    for k, v in fields.items():
        if k in _NUMERIC_KEYS:
            try:
                extraction[k] = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                extraction[k] = None
        else:
            extraction[k] = v if v not in (None, "") else None
    return {
        "doc_type": doc_type,
        "source_file": filename,
        "extraction": extraction,
    }


# ─────────────────────────────────────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    try:
        conn = _get_db()
        try:
            payload = _build_dashboard_payload(conn)
        finally:
            conn.close()
        return jsonify(payload)
    except Exception as exc:
        log.error("Dashboard error:\n%s", traceback.format_exc())
        return jsonify({"error": str(exc)}), 503


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    try:
        conn = _get_db()
        try:
            run_all_calculations(conn)
        finally:
            conn.close()
        return "", 204
    except Exception as exc:
        log.error("Refresh error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Receive a document file → Doc AI OCR → classify → Gemini extraction
    → return structured review fields for human verification.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

    suffix = Path(uploaded.filename).suffix.lower() or ".pdf"
    log.info("[upload] received file: %s (suffix=%s)", uploaded.filename, suffix)

    try:
        config = get_config()
        log.info("[upload] config loaded OK")
    except Exception as exc:
        log.error("[upload] config error: %s", exc)
        return jsonify({"error": f"Server configuration error: {exc}"}), 500

    # ── Lazy imports (require google-cloud-documentai + gemini) ──────────
    try:
        from src.docai_client import build_client, process_pdf          # noqa: PLC0415
        from src.docai_normalize import normalize, build_enriched_text  # noqa: PLC0415
        from src.classify import classify_doc_with_scores               # noqa: PLC0415
        from src.extractors.utility_extractor import extract_utility    # noqa: PLC0415
        from src.extractors.invoice_extractor import extract_invoice    # noqa: PLC0415
        from src.extractors.logistics_extractor import extract_logistics # noqa: PLC0415
        log.info("[upload] all imports OK")
    except ImportError as exc:
        log.error("[upload] import error: %s", exc)
        return jsonify({"error": f"Document AI packages not installed: {exc}"}), 501

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            uploaded.save(tmp_path)
        log.info("[upload] saved temp file: %s (%d bytes)", tmp_path, tmp_path.stat().st_size)

        # ── 1. Doc AI (Form Processor for generic OCR + classify) ────────
        log.info("[upload] building Doc AI client…")
        client = build_client(config)
        log.info("[upload] sending to Doc AI processor: %s", config.docai_form_processor_name)
        docai_doc = process_pdf(
            pdf_path=tmp_path,
            config=config,
            client=client,
            processor_name=config.docai_form_processor_name,
        )
        normalized = normalize(docai_doc)
        enriched = build_enriched_text(normalized)
        log.info("[upload] Doc AI returned %d chars, %d pages", len(normalized.full_text), normalized.page_count)

        # ── 2. Classify document type ─────────────────────────────────────
        doc_type, scores = classify_doc_with_scores(normalized.full_text)
        log.info("[upload] classified as '%s'  scores=%s", doc_type, scores)

        # ── 3. Gemini structured extraction ──────────────────────────────
        warnings: list[str] = []
        log.info("[upload] running Gemini extractor for type '%s'…", doc_type)
        if doc_type == DOC_TYPE_UTILITY_BILL:
            extraction = extract_utility(enriched, config, warnings)
        elif doc_type in (DOC_TYPE_DELIVERY_RECEIPT, DOC_TYPE_LOGISTICS):
            extraction = extract_logistics(enriched, config, warnings)
            doc_type = DOC_TYPE_DELIVERY_RECEIPT
        elif doc_type in (DOC_TYPE_INVOICE, DOC_TYPE_RECEIPT):
            extraction = extract_invoice(enriched, config, warnings)
            doc_type = DOC_TYPE_INVOICE
        else:
            # Unknown – best-effort as invoice
            extraction = extract_invoice(enriched, config, warnings)
            doc_type = DOC_TYPE_INVOICE
        log.info("[upload] extraction keys: %s  warnings: %s", list(extraction.keys()), warnings)

        # ── 4. Build human-readable review fields ────────────────────────
        if doc_type == DOC_TYPE_UTILITY_BILL:
            tmp_payload = {"doc_type": doc_type, "extraction": extraction}
            subtype = resolve_utility_subtype(tmp_payload) or "electricity"
            fields = _utility_review_fields(extraction, subtype)
        elif doc_type == DOC_TYPE_DELIVERY_RECEIPT:
            fields = _logistics_review_fields(extraction)
        else:
            fields = _invoice_review_fields(extraction)

        log.info("[upload] returning %d fields for doc_type='%s'", len(fields), doc_type)

        # ── Save extraction.json for debugging (mirrors CLI behaviour) ────
        try:
            import json as _json
            stem = Path(uploaded.filename).stem
            out_dir = _here / "out" / stem
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "extraction.json").write_text(
                _json.dumps(extraction, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
            log.info("[upload] extraction saved → out/%s/extraction.json", stem)
        except Exception as _e:
            log.warning("[upload] could not save extraction.json: %s", _e)

        return jsonify({
            "doc_type": doc_type,
            "fields": fields,
            "warnings": warnings,
        })

    except Exception as exc:
        log.error("[upload] FAILED:\n%s", traceback.format_exc())
        return jsonify({"error": str(exc)}), 500

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    """
    Receive human-confirmed extraction fields → insert document + parsed row
    → re-run calculations → return updated dashboard payload.
    """
    body = request.get_json(force=True)
    doc_type: str = body.get("doc_type", "unknown")
    fields: dict[str, str] = body.get("fields", {})
    filename: str = body.get("filename", "")

    payload = _build_confirm_payload(doc_type, fields, filename)

    try:
        conn = _get_db()
        try:
            doc_id = insert_document(conn, payload)
            insert_category(conn, doc_id, payload)
            conn.commit()
            run_all_calculations(conn)
            dashboard = _build_dashboard_payload(conn)
        finally:
            conn.close()
        return jsonify({"ok": True, "document_id": doc_id, "dashboard": dashboard})
    except Exception as exc:
        log.error("Confirm error:\n%s", traceback.format_exc())
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Static file serving – React build
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path: str):
    if not _DIST.exists():
        return (
            "React build not found. Run  npm run build  inside dashboard/  first.",
            404,
        )
    target = _DIST / path
    if path and target.exists():
        return send_from_directory(str(_DIST), path)
    # SPA fallback – let React Router handle the URL
    return send_from_directory(str(_DIST), "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    log.info("Starting SME Sustainability Pulse on http://localhost:%d", port)
    # use_reloader=False prevents watchdog from restarting on stdlib file changes
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
