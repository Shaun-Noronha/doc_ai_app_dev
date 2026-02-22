"""
emission_factors.py – Emission factor constants used in GHG calculations.

All factors are in kg CO₂e per unit unless noted.
Sources: US EPA GHG Emission Factors Hub (2024), IPCC AR6.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# Scope 2 – Purchased Electricity (kg CO₂e / kWh)
# US EPA eGRID sub-region average factors (2022 data).
# Key: lowercase city or state abbreviation → factor
# Fallback: US national average.
# ─────────────────────────────────────────────────────────────
DEFAULT_ELECTRICITY_FACTOR: float = 0.386   # US national avg (kg CO₂e/kWh)

ELECTRICITY_FACTORS_BY_REGION: dict[str, float] = {
    # State abbreviations (lower)
    "ca": 0.198,   # California – heavy renewables
    "wa": 0.095,   # Washington – mostly hydro
    "tx": 0.418,   # Texas – ERCOT
    "ny": 0.228,   # New York
    "fl": 0.407,   # Florida
    "il": 0.393,   # Illinois
    "pa": 0.344,   # Pennsylvania
    "oh": 0.485,   # Ohio – coal-heavy
    "ga": 0.388,   # Georgia
    "co": 0.506,   # Colorado
    # Full state name fragments (lower, first word)
    "california": 0.198,
    "washington": 0.095,
    "texas": 0.418,
    "new": 0.228,       # New York / New Jersey / New Mexico (rough)
    "florida": 0.407,
    "illinois": 0.393,
    "pennsylvania": 0.344,
    "ohio": 0.485,
    "georgia": 0.388,
    "colorado": 0.506,
}


def get_electricity_factor(location: str | None) -> float:
    """
    Return the best-match emission factor (kg CO₂e/kWh) for a given location string.
    Location format expected: 'City, ST' or 'ST' or 'State Name'.
    Falls back to the US national average when no match is found.
    """
    if not location:
        return DEFAULT_ELECTRICITY_FACTOR

    parts = [p.strip().lower() for p in location.replace(",", " ").split()]
    for part in parts:
        if part in ELECTRICITY_FACTORS_BY_REGION:
            return ELECTRICITY_FACTORS_BY_REGION[part]
    return DEFAULT_ELECTRICITY_FACTOR


# ─────────────────────────────────────────────────────────────
# Scope 1 – Stationary Fuel Combustion (kg CO₂e per unit)
# ─────────────────────────────────────────────────────────────
STATIONARY_FUEL_FACTORS: dict[str, dict[str, float]] = {
    # natural_gas
    "natural_gas": {
        "therms": 5.302,        # kg CO₂e / therm  (EPA)
        "ccf":    5.302,        # 1 CCF ≈ 1 therm for natural gas
        "mcf":   53.02,         # 1 MCF = 10 therms
        "cubic_feet": 0.05302,  # per ft³
        "m3": 1.879,            # per cubic metre
        "kg": 2.744,            # per kg of natural gas
    },
    "propane": {
        "gallons": 5.720,       # kg CO₂e / gallon
        "liters":  1.512,       # per litre
        "kg":      2.994,       # per kg
    },
    "heating_oil": {
        "gallons": 10.21,       # kg CO₂e / gallon (same as diesel)
        "liters":   2.698,
    },
    "diesel": {
        "gallons": 10.21,
        "liters":   2.698,
    },
    "coal": {
        "kg": 2.42,
        "short_tons": 2196.17,
    },
}

# Default factor when fuel type is unknown (uses natural gas therms as fallback)
DEFAULT_STATIONARY_FACTOR: float = 5.302
DEFAULT_STATIONARY_UNIT: str = "therms"


def get_stationary_fuel_factor(fuel_type: str | None, unit: str | None) -> float:
    """Return kg CO₂e per unit for stationary fuel combustion."""
    ft = (fuel_type or "natural_gas").lower().replace(" ", "_").replace("-", "_")
    u = (unit or DEFAULT_STATIONARY_UNIT).lower().replace(" ", "_")
    fuel_map = STATIONARY_FUEL_FACTORS.get(ft, STATIONARY_FUEL_FACTORS["natural_gas"])
    return fuel_map.get(u, DEFAULT_STATIONARY_FACTOR)


# ─────────────────────────────────────────────────────────────
# Scope 1 – Vehicle / Mobile Fuel Combustion (kg CO₂e per unit)
# ─────────────────────────────────────────────────────────────
VEHICLE_FUEL_FACTORS: dict[str, dict[str, float]] = {
    "gasoline": {
        "gallon": 8.887,    # kg CO₂e / US gallon (EPA)
        "liter":  2.347,    # per litre
        "litre":  2.347,
    },
    "diesel": {
        "gallon": 10.210,   # kg CO₂e / US gallon
        "liter":   2.698,
        "litre":   2.698,
    },
    "e85": {           # 85 % ethanol blend
        "gallon": 5.750,
        "liter":  1.519,
    },
    "cng": {           # Compressed natural gas (per SCF)
        "scf": 0.0543,
        "kg":  2.744,
    },
}

DEFAULT_VEHICLE_FACTOR: float = 8.887  # gasoline / gallon


def get_vehicle_fuel_factor(fuel_type: str | None, unit: str | None) -> float:
    """Return kg CO₂e per unit for vehicle / mobile fuel combustion."""
    ft = (fuel_type or "gasoline").lower().replace(" ", "_")
    u = (unit or "gallon").lower().replace(" ", "_").rstrip("s")  # normalise plural
    fuel_map = VEHICLE_FUEL_FACTORS.get(ft, VEHICLE_FUEL_FACTORS["gasoline"])
    return fuel_map.get(u, DEFAULT_VEHICLE_FACTOR)


# ─────────────────────────────────────────────────────────────
# Scope 3 – Transportation & Shipping (kg CO₂e per ton-mile)
# Source: EPA MOVES / IPCC / SmartWay (2023)
# ─────────────────────────────────────────────────────────────
TRANSPORT_MODE_FACTORS: dict[str, float] = {
    "truck":  0.161,    # kg CO₂e / ton-mile (heavy-duty trucking)
    "rail":   0.031,    # freight rail
    "sea":    0.015,    # ocean freight
    "air":    2.126,    # air freight (long-haul)
    "ship":   0.015,    # alias for sea
    "ocean":  0.015,
    "barge":  0.040,
    "van":    0.200,    # light commercial vehicle
}

DEFAULT_TRANSPORT_FACTOR: float = 0.161  # truck default


def get_transport_factor(mode: str | None) -> float:
    """Return kg CO₂e per ton-mile for the given transport mode."""
    m = (mode or "truck").lower().strip()
    return TRANSPORT_MODE_FACTORS.get(m, DEFAULT_TRANSPORT_FACTOR)


# ─────────────────────────────────────────────────────────────
# Scope 3 – Waste Generation (kg CO₂e per kg of waste)
# Source: EPA WARM model (2023)
# ─────────────────────────────────────────────────────────────
WASTE_DISPOSAL_FACTORS: dict[str, float] = {
    "landfill":   1.900,   # kg CO₂e / kg waste (mixed municipal solid waste)
    "recycle":    0.000,   # No direct emission (beneficial – conservative 0)
    "compost":    0.100,   # Low biogenic methane release
    "incinerate": 0.500,   # Energy-recovery incineration (net of avoided landfill)
    "incineration": 0.500,
}

DEFAULT_WASTE_FACTOR: float = 1.900  # landfill default


def get_waste_factor(disposal_method: str | None) -> float:
    """Return kg CO₂e per kg of waste for the given disposal method."""
    m = (disposal_method or "landfill").lower().strip()
    return WASTE_DISPOSAL_FACTORS.get(m, DEFAULT_WASTE_FACTOR)


# ─────────────────────────────────────────────────────────────
# Unit conversion helpers
# ─────────────────────────────────────────────────────────────
LB_TO_KG: float = 0.453592
KG_TO_LB: float = 2.20462
GALLON_TO_LITER: float = 3.78541
LITER_TO_GALLON: float = 0.264172
KM_TO_MILES: float = 0.621371
MILES_TO_KM: float = 1.60934


def to_kg(value: float, unit: str) -> float:
    """Convert a weight value to kilograms."""
    u = unit.lower().rstrip("s")  # normalise plural
    if u in ("kg", "kilogram"):
        return value
    if u in ("lb", "lbs", "pound"):
        return value * LB_TO_KG
    if u in ("ton", "metric_ton", "mt", "tonne"):
        return value * 1_000.0
    if u in ("short_ton", "us_ton"):
        return value * 907.185
    return value  # assume kg if unknown


def to_gallons(value: float, unit: str) -> float:
    """Convert a volume value to US gallons."""
    u = unit.lower().rstrip("s")
    if u in ("gallon", "gal", "us_gallon"):
        return value
    if u in ("liter", "litre", "l"):
        return value * LITER_TO_GALLON
    return value  # assume gallons if unknown
