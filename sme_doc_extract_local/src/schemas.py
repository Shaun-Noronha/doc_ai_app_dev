"""
schemas.py – Pydantic models for each supported document type.

All date fields use ISO 8601 (YYYY-MM-DD).
All numeric fields are float or int; None means the value was absent
in the source document.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Shared / sub-models
# ─────────────────────────────────────────────────────────────

class LineItem(BaseModel):
    """A single line on an invoice."""

    description: Optional[str] = Field(None, description="Item description")
    quantity: Optional[float] = Field(None, description="Number of units")
    unit_price: Optional[float] = Field(None, description="Price per unit")
    total_price: Optional[float] = Field(None, description="Line total")


class Location(BaseModel):
    """A geographic location."""

    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Invoice
# ─────────────────────────────────────────────────────────────

class InvoiceSchema(BaseModel):
    """Structured fields extracted from an invoice / purchase order."""

    vendor_name: Optional[str] = Field(None, description="Name of the vendor or supplier")
    invoice_number: Optional[str] = Field(None, description="Invoice or PO reference number")
    invoice_date: Optional[str] = Field(None, description="Issue date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(None, description="Payment due date in YYYY-MM-DD format")
    currency: Optional[str] = Field(None, description="ISO 4217 currency code, e.g. USD")
    subtotal: Optional[float] = Field(None, description="Pre-tax subtotal")
    tax: Optional[float] = Field(None, description="Tax amount")
    total: Optional[float] = Field(None, description="Grand total")
    line_items: list[LineItem] = Field(default_factory=list, description="Invoice line items")


# ─────────────────────────────────────────────────────────────
# Utility Bill
# ─────────────────────────────────────────────────────────────

class UtilitySchema(BaseModel):
    """Structured fields extracted from a utility bill."""

    provider: Optional[str] = Field(None, description="Utility company name")
    account_id: Optional[str] = Field(None, description="Customer / account number")
    billing_period_start: Optional[str] = Field(None, description="Billing period start YYYY-MM-DD")
    billing_period_end: Optional[str] = Field(None, description="Billing period end YYYY-MM-DD")
    electricity_kwh: Optional[float] = Field(None, description="Electricity usage in kWh")
    natural_gas_therms: Optional[float] = Field(None, description="Natural gas usage in therms")
    total_amount: Optional[float] = Field(None, description="Total amount due")
    currency: Optional[str] = Field(None, description="ISO 4217 currency code")


# ─────────────────────────────────────────────────────────────
# Logistics / Shipping
# ─────────────────────────────────────────────────────────────

class LogisticsSchema(BaseModel):
    """Structured fields extracted from a logistics / shipping document."""

    shipment_id: Optional[str] = Field(None, description="Shipment or BOL reference number")
    date: Optional[str] = Field(None, description="Shipment or document date YYYY-MM-DD")
    carrier: Optional[str] = Field(None, description="Carrier or freight company name")
    mode: Optional[Literal["truck", "air", "sea", "rail"]] = Field(
        None, description="Transport mode"
    )
    origin: Optional[Location] = Field(None, description="Origin location")
    destination: Optional[Location] = Field(None, description="Destination location")
    distance_km: Optional[float] = Field(None, description="Distance in kilometres")
    weight_kg: Optional[float] = Field(None, description="Total shipment weight in kg")
    packages_count: Optional[int] = Field(None, description="Number of packages")


# ─────────────────────────────────────────────────────────────
# Union helper
# ─────────────────────────────────────────────────────────────

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "invoice": InvoiceSchema,
    "utility": UtilitySchema,
    "logistics": LogisticsSchema,
}
