"""
emission_factors.py – Standard emission factors (kg CO2e per unit).

Sources: US EPA Emission Factors for Greenhouse Gas Inventories (2023),
DEFRA UK Government GHG Conversion Factors.

All values are kg CO2e per unit unless otherwise noted.
"""
from __future__ import annotations

# ─── Scope 2 ───────────────────────────────────────────────────────────────
# Electricity (kg CO2e / kWh) – US national average grid (EPA eGRID 2023)
ELECTRICITY_KG_PER_KWH: float = 0.3862

# ─── Scope 1 ───────────────────────────────────────────────────────────────
# Stationary fuel combustion (kg CO2e / unit)
STATIONARY_FUEL_KG: dict[str, dict[str, float]] = {
    # natural_gas: 5.3 kg CO2e / therm (EPA 2023), also ft3 / gallon (HHV)
    "natural_gas": {
        "therm": 5.3067,
        "ft3": 0.0549,       # 1 therm ≈ 96.7 ft3; 5.3067 / 96.7
        "gallon": 5.3067,    # fallback; not typical for natural gas
    },
    "propane": {
        "gallon": 5.7260,    # EPA: 5.72 kg CO2e / gallon propane
        "therm": 6.3200,
        "ft3": 0.0680,
    },
    "heating_oil": {
        "gallon": 10.1530,   # EPA: 10.15 kg CO2e / gallon #2 fuel oil
        "therm": 7.4100,
        "ft3": 0.0001,       # not standard; use gallon
    },
}

# Vehicle fuel combustion (kg CO2e / gallon)
VEHICLE_FUEL_KG: dict[str, dict[str, float]] = {
    "gasoline": {
        "gallon": 8.8878,    # EPA: 8.89 kg CO2e / gallon gasoline
        "liter": 2.3480,     # 8.8878 / 3.785
    },
    "diesel": {
        "gallon": 10.1800,   # EPA: 10.18 kg CO2e / gallon diesel
        "liter": 2.6893,
    },
}

# ─── Scope 3 ───────────────────────────────────────────────────────────────
# Shipping / freight (kg CO2e / ton-mile) – EPA MOVES / DEFRA 2023
SHIPPING_KG_PER_TON_MILE: dict[str, float] = {
    "truck": 0.1693,
    "ship":  0.0098,
    "rail":  0.0229,
    "air":   1.1300,
    None:    0.1693,   # default to truck when mode is unknown
}

# Waste disposal (kg CO2e / kg waste) – EPA WARM model typical values
WASTE_KG_PER_KG: dict[str, float] = {
    "landfill":   0.4460,   # biogenic + methane
    "incinerate": 0.0980,
    "recycle":    0.0000,   # avoided emissions counted as 0 here (conservative)
    "compost":    0.0100,
}

# ─── Unit converters ───────────────────────────────────────────────────────
GALLON_TO_M3: float = 0.00378541
LB_TO_KG: float = 0.453592
