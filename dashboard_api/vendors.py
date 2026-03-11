"""
vendors.py – List vendors and get/set selected vendors for the frontend.
"""
from __future__ import annotations

from . import db


def get_vendors() -> list[dict]:
    """
    Return all vendors: vendor_id, vendor_name, category, product_or_service,
    carbon_intensity, sustainability_score, distance_km_from_sme.
    """
    rows = db.query(
        """
        SELECT vendor_id, vendor_name, category, product_or_service,
               carbon_intensity, sustainability_score, distance_km_from_sme
        FROM vendors
        ORDER BY sustainability_score DESC, vendor_name
        """
    )
    return [_row_to_vendor(r) for r in rows]


def get_selected_vendor_ids() -> list[str]:
    """Return list of selected vendor_id (order by selected_at)."""
    rows = db.query(
        "SELECT vendor_id FROM selected_vendors ORDER BY selected_at"
    )
    return [str(r["vendor_id"]) for r in rows]


def set_selected_vendors(vendor_ids: list[str]) -> None:
    """
    Replace current selection with the given vendor_ids.
    Invalid ids are ignored (only ids present in vendors are inserted).
    """
    def do_set(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM selected_vendors")
            if vendor_ids:
                cur.execute(
                    "SELECT vendor_id FROM vendors WHERE vendor_id = ANY(%s)",
                    (vendor_ids,),
                )
                valid = {row[0] for row in cur.fetchall()}
                for vid in vendor_ids:
                    if vid in valid:
                        cur.execute(
                            "INSERT INTO selected_vendors (vendor_id) VALUES (%s)",
                            (vid,),
                        )
        conn.commit()

    db.with_connection(do_set)


def _row_to_vendor(r: dict) -> dict:
    """Convert DB row to JSON-serializable vendor dict."""
    return {
        "vendor_id": r.get("vendor_id"),
        "vendor_name": r.get("vendor_name"),
        "category": r.get("category"),
        "product_or_service": r.get("product_or_service"),
        "carbon_intensity": float(r["carbon_intensity"]) if r.get("carbon_intensity") is not None else 0,
        "sustainability_score": int(r["sustainability_score"]) if r.get("sustainability_score") is not None else 0,
        "distance_km_from_sme": float(r["distance_km_from_sme"]) if r.get("distance_km_from_sme") is not None else None,
    }
