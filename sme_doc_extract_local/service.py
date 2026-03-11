"""
service.py – Callable upload/confirm logic for the Doc AI pipeline.

Used by the FastAPI backend (dashboard_api) for POST /api/upload and POST /api/confirm.
No Flask dependency. Run with repo root or sme_doc_extract_local on sys.path.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from dotenv import load_dotenv

for _env in (_here / ".env", _here.parent / ".env"):
    if _env.exists():
        load_dotenv(_env)
        break

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

log = logging.getLogger(__name__)


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
# Upload helpers – per-doc-type review fields
# ─────────────────────────────────────────────────────────────────────────────

def _utility_review_fields(extraction: dict, subtype: str) -> list[dict]:
    fields: list[dict] = [
        {"key": "utility_type",          "label": "Utility Type",      "value": subtype,                                   "editable": True},
        {"key": "location",              "label": "Location",          "value": extraction.get("location"),                "editable": True},
        {"key": "billing_period_start",  "label": "Period Start",      "value": extraction.get("billing_period_start"),    "editable": True},
        {"key": "billing_period_end",    "label": "Period End",        "value": extraction.get("billing_period_end"),      "editable": True},
    ]
    if subtype == "electricity":
        fields.append({"key": "electricity_kwh",     "label": "Electricity (kWh)",  "value": extraction.get("electricity_kwh"),     "editable": True})
    elif subtype == "gas":
        fields.append({"key": "natural_gas_therms",  "label": "Gas (therms)",       "value": extraction.get("natural_gas_therms"),  "editable": True})
    elif subtype == "water":
        fields.append({"key": "water_volume",        "label": "Water Volume",       "value": extraction.get("water_volume"),        "editable": True})
        fields.append({"key": "water_unit",          "label": "Unit",               "value": extraction.get("water_unit") or "gallon", "editable": True})
    return fields


def _logistics_review_fields(extraction: dict) -> list[dict]:
    origin = extraction.get("origin") or {}
    dest   = extraction.get("destination") or {}
    origin_str = ", ".join(filter(None, [origin.get("city"), origin.get("state"), origin.get("country")]))
    dest_str   = ", ".join(filter(None, [dest.get("city"),   dest.get("state"),   dest.get("country")]))
    return [
        {"key": "shipment_id",  "label": "Shipment ID",    "value": extraction.get("shipment_id"),    "editable": True},
        {"key": "carrier",      "label": "Carrier",        "value": extraction.get("carrier"),        "editable": True},
        {"key": "mode",         "label": "Transport Mode", "value": extraction.get("mode"),           "editable": True},
        {"key": "date",         "label": "Shipment Date",  "value": extraction.get("date"),           "editable": True},
        {"key": "origin",       "label": "Origin",         "value": origin_str or None,               "editable": True},
        {"key": "destination",  "label": "Destination",    "value": dest_str or None,                 "editable": True},
        {"key": "weight_kg",    "label": "Weight (kg)",    "value": extraction.get("weight_kg"),      "editable": True},
        {"key": "distance_km",  "label": "Distance (km)",  "value": extraction.get("distance_km"),    "editable": True},
        {"key": "packages_count","label": "Packages",      "value": extraction.get("packages_count"), "editable": True},
    ]


def _invoice_review_fields(extraction: dict) -> list[dict]:
    return [
        {"key": "vendor_name",    "label": "Vendor",        "value": extraction.get("vendor_name"),    "editable": True},
        {"key": "invoice_number", "label": "Invoice No.",   "value": extraction.get("invoice_number"), "editable": True},
        {"key": "invoice_date",   "label": "Invoice Date",  "value": extraction.get("invoice_date"),   "editable": True},
        {"key": "due_date",       "label": "Due Date",      "value": extraction.get("due_date"),       "editable": True},
        {"key": "subtotal",       "label": "Subtotal",      "value": extraction.get("subtotal"),       "editable": True},
        {"key": "tax",            "label": "Tax",           "value": extraction.get("tax"),            "editable": True},
        {"key": "total",          "label": "Total",         "value": extraction.get("total"),          "editable": True},
        {"key": "currency",       "label": "Currency",      "value": extraction.get("currency"),       "editable": True},
    ]


def handle_upload(file_bytes: bytes, filename: str, suffix: str) -> dict:
    """
    Run Doc AI + classify + Gemini extraction on the given file bytes.
    Returns {"doc_type", "fields", "warnings"} for human review.
    Raises RuntimeError with a message if config or imports fail.
    """
    log.info("[upload] received file: %s (suffix=%s)", filename, suffix)

    try:
        config = get_config()
        log.info("[upload] config loaded OK")
    except Exception as exc:
        log.error("[upload] config error: %s", exc)
        raise RuntimeError(f"Server configuration error: {exc}") from exc

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
        raise RuntimeError(f"Document AI packages not installed: {exc}") from exc

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        log.info("[upload] saved temp file: %s (%d bytes)", tmp_path, len(file_bytes))

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

        doc_type, scores = classify_doc_with_scores(normalized.full_text)
        log.info("[upload] classified as '%s'  scores=%s", doc_type, scores)

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
            extraction = extract_invoice(enriched, config, warnings)
            doc_type = DOC_TYPE_INVOICE
        log.info("[upload] extraction keys: %s  warnings: %s", list(extraction.keys()), warnings)

        if doc_type == DOC_TYPE_UTILITY_BILL:
            tmp_payload = {"doc_type": doc_type, "extraction": extraction}
            subtype = resolve_utility_subtype(tmp_payload) or "electricity"
            fields = _utility_review_fields(extraction, subtype)
        elif doc_type == DOC_TYPE_DELIVERY_RECEIPT:
            fields = _logistics_review_fields(extraction)
        else:
            fields = _invoice_review_fields(extraction)

        log.info("[upload] returning %d fields for doc_type='%s'", len(fields), doc_type)

        try:
            import json as _json
            stem = Path(filename).stem
            out_dir = _here / "out" / stem
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "extraction.json").write_text(
                _json.dumps(extraction, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
            log.info("[upload] extraction saved → out/%s/extraction.json", stem)
        except Exception as _e:
            log.warning("[upload] could not save extraction.json: %s", _e)

        return {
            "doc_type": doc_type,
            "fields": fields,
            "warnings": warnings,
        }

    except Exception as exc:
        log.error("[upload] FAILED:\n%s", traceback.format_exc())
        raise

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def handle_confirm(body: dict) -> int:
    """
    Build confirm payload from body (doc_type, fields, filename), insert document
    and category, run calculations. Returns document_id. Caller should then
    fetch dashboard via queries.get_dashboard_live() if needed.
    """
    doc_type: str = body.get("doc_type", "unknown")
    fields: dict[str, str] = body.get("fields", {})
    filename: str = body.get("filename", "")

    payload = _build_confirm_payload(doc_type, fields, filename)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in the environment.")

    conn = get_connection(url)
    try:
        doc_id = insert_document(conn, payload)
        insert_category(conn, doc_id, payload)
        conn.commit()
        run_all_calculations(conn)
        return doc_id
    finally:
        conn.close()
