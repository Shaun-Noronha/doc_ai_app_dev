"""
validators.py – Post-extraction validation, normalisation, and confidence scoring.

Each ``validate_*`` function:
* Accepts a raw dict from Gemini.
* Returns a (normalised_dict, warnings_list, confidence_map) tuple.

Normalisation steps
-------------------
* Parse and reformat dates to ISO YYYY-MM-DD.
* Strip commas / currency symbols from numeric fields and cast to float.
* Clamp logistics mode to the allowed set or null.

Validation checks add warnings but do NOT remove data – the caller decides
whether to propagate warnings to the output.
"""
from __future__ import annotations

import re
from typing import Any

from dateutil import parser as dateutil_parser

from src.constants import (
    CONFIDENCE_MISSING,
    CONFIDENCE_PRESENT_INVALID,
    CONFIDENCE_PRESENT_VALID,
    INVOICE_TOTAL_TOLERANCE,
    LOGISTICS_ALLOWED_MODES,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    """
    Try to convert *value* to float.

    Strips commas, spaces, and common currency prefixes/suffixes before
    conversion.  Returns None on failure.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[,$€£¥\s]", "", value)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_iso_date(value: Any) -> str | None:
    """
    Parse *value* as a date and return YYYY-MM-DD string.

    Accepts: Python date/datetime objects, ISO strings, common formats like
    ``MM/DD/YYYY``, ``DD-Mon-YYYY``, etc.  Returns None on failure.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Already ISO?
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
    try:
        dt = dateutil_parser.parse(str(value), dayfirst=False)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _confidence(value: Any, valid: bool) -> float:
    """Return a simple confidence score for *value*."""
    if value is None:
        return CONFIDENCE_MISSING
    return CONFIDENCE_PRESENT_VALID if valid else CONFIDENCE_PRESENT_INVALID


# ─────────────────────────────────────────────────────────────
# Invoice
# ─────────────────────────────────────────────────────────────

def validate_invoice(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """
    Normalise and validate an invoice extraction dict.

    Returns
    -------
    (normalised_dict, warnings, confidence_map)
    """
    warnings: list[str] = []
    conf: dict[str, float] = {}
    d = dict(raw)

    # -- Numeric fields --
    for field in ("subtotal", "tax", "total"):
        d[field] = _to_float(d.get(field))

    # -- Date fields --
    for field in ("invoice_date", "due_date"):
        original = d.get(field)
        d[field] = _to_iso_date(original)
        if original and d[field] is None:
            warnings.append(f"Could not parse {field}: '{original}'")

    # -- Line items --
    normalised_items = []
    for item in d.get("line_items") or []:
        ni = dict(item) if isinstance(item, dict) else {}
        ni["quantity"] = _to_float(ni.get("quantity"))
        ni["unit_price"] = _to_float(ni.get("unit_price"))
        ni["total_price"] = _to_float(ni.get("total_price"))
        normalised_items.append(ni)
    d["line_items"] = normalised_items

    # -- Consistency check: subtotal + tax ≈ total --
    sub = d.get("subtotal")
    tax = d.get("tax")
    total = d.get("total")

    total_consistent = True
    if sub is not None and tax is not None and total is not None:
        calc = sub + tax
        diff = abs(calc - total)
        if diff > INVOICE_TOTAL_TOLERANCE:
            warnings.append(
                f"Total mismatch: subtotal ({sub}) + tax ({tax}) = {calc:.2f} "
                f"but total is {total} (diff={diff:.2f})"
            )
            total_consistent = False

    if total is not None and total < 0:
        warnings.append(f"total is negative ({total})")

    # -- Confidence --
    conf["vendor_name"] = _confidence(d.get("vendor_name"), True)
    conf["invoice_number"] = _confidence(d.get("invoice_number"), True)
    conf["invoice_date"] = _confidence(d.get("invoice_date"), d.get("invoice_date") is not None)
    conf["subtotal"] = _confidence(sub, sub is None or sub >= 0)
    conf["tax"] = _confidence(tax, tax is None or tax >= 0)
    conf["total"] = _confidence(total, total_consistent and (total is None or total >= 0))

    return d, warnings, conf


# ─────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────

def validate_utility(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """
    Normalise and validate a utility-bill extraction dict.

    Returns
    -------
    (normalised_dict, warnings, confidence_map)
    """
    warnings: list[str] = []
    conf: dict[str, float] = {}
    d = dict(raw)

    # -- Numeric fields --
    for field in ("electricity_kwh", "natural_gas_therms", "total_amount"):
        d[field] = _to_float(d.get(field))

    # -- Date fields --
    for field in ("billing_period_start", "billing_period_end"):
        original = d.get(field)
        d[field] = _to_iso_date(original)
        if original and d[field] is None:
            warnings.append(f"Could not parse {field}: '{original}'")

    # -- Period order --
    start = d.get("billing_period_start")
    end = d.get("billing_period_end")
    period_valid = True
    if start and end:
        if start > end:
            warnings.append(
                f"billing_period_start ({start}) is after billing_period_end ({end})"
            )
            period_valid = False

    # -- Non-negative usage --
    kwh = d.get("electricity_kwh")
    if kwh is not None and kwh < 0:
        warnings.append(f"electricity_kwh is negative ({kwh})")

    therms = d.get("natural_gas_therms")
    if therms is not None and therms < 0:
        warnings.append(f"natural_gas_therms is negative ({therms})")

    # -- Confidence --
    conf["provider"] = _confidence(d.get("provider"), True)
    conf["account_id"] = _confidence(d.get("account_id"), True)
    conf["billing_period_start"] = _confidence(start, period_valid and start is not None)
    conf["billing_period_end"] = _confidence(end, period_valid and end is not None)
    conf["electricity_kwh"] = _confidence(kwh, kwh is None or kwh >= 0)
    conf["total_amount"] = _confidence(d.get("total_amount"), True)

    return d, warnings, conf


# ─────────────────────────────────────────────────────────────
# Logistics
# ─────────────────────────────────────────────────────────────

def validate_logistics(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """
    Normalise and validate a logistics extraction dict.

    Returns
    -------
    (normalised_dict, warnings, confidence_map)
    """
    warnings: list[str] = []
    conf: dict[str, float] = {}
    d = dict(raw)

    # -- Numeric fields --
    for field in ("distance_km", "weight_kg"):
        d[field] = _to_float(d.get(field))

    packages = d.get("packages_count")
    if packages is not None:
        try:
            d["packages_count"] = int(packages)
        except (ValueError, TypeError):
            warnings.append(f"packages_count '{packages}' is not an integer; setting null")
            d["packages_count"] = None

    # -- Date --
    original_date = d.get("date")
    d["date"] = _to_iso_date(original_date)
    if original_date and d["date"] is None:
        warnings.append(f"Could not parse date: '{original_date}'")

    # -- Mode --
    mode = d.get("mode")
    mode_valid = True
    if mode is not None:
        mode_lower = str(mode).lower().strip()
        if mode_lower in LOGISTICS_ALLOWED_MODES:
            d["mode"] = mode_lower
        else:
            warnings.append(
                f"mode '{mode}' is not allowed; expected one of "
                f"{sorted(LOGISTICS_ALLOWED_MODES)}. Setting null."
            )
            d["mode"] = None
            mode_valid = False

    # -- Non-negative numerics --
    dist = d.get("distance_km")
    if dist is not None and dist < 0:
        warnings.append(f"distance_km is negative ({dist})")

    weight = d.get("weight_kg")
    if weight is not None and weight < 0:
        warnings.append(f"weight_kg is negative ({weight})")

    # -- Confidence --
    conf["shipment_id"] = _confidence(d.get("shipment_id"), True)
    conf["carrier"] = _confidence(d.get("carrier"), True)
    conf["mode"] = _confidence(d.get("mode"), mode_valid)
    conf["origin"] = _confidence(d.get("origin"), True)
    conf["destination"] = _confidence(d.get("destination"), True)
    conf["distance_km"] = _confidence(dist, dist is None or dist >= 0)
    conf["weight_kg"] = _confidence(weight, weight is None or weight >= 0)

    return d, warnings, conf


# ─────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────

_VALIDATOR_MAP = {
    "invoice": validate_invoice,
    "utility": validate_utility,
    "logistics": validate_logistics,
}


def validate(
    doc_type: str,
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, float]]:
    """
    Dispatch to the correct validator based on *doc_type*.

    Falls back to returning the raw dict unchanged if the type is unknown.
    """
    fn = _VALIDATOR_MAP.get(doc_type)
    if fn is None:
        return raw, [f"No validator for doc_type='{doc_type}'"], {}
    return fn(raw)
