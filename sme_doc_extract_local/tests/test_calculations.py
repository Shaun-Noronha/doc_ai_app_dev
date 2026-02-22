"""
Unit tests for src/calculations.py

No real DB connection is used. Each test builds a mock psycopg2 connection
that satisfies the `with conn.cursor() as cur:` pattern used in calculations.py.
_upsert_activity and _upsert_emission are patched out so only the
calculation math is exercised.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from src.calculations import (
    calc_electricity_emissions,
    calc_stationary_fuel_emissions,
    calc_vehicle_fuel_emissions,
    calc_shipping_emissions,
    calc_waste_emissions,
    calc_water_metrics,
    calc_energy_intensity,
    calc_waste_diversion_rate,
    calc_ghg_summary,
    EmissionResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a mock psycopg2 connection
#
# calculations.py always does:
#     with conn.cursor() as cur:
#         cur.execute(...)
#         rows = cur.fetchall()   # or cur.fetchone()
#
# The mock must support that context-manager protocol.
# ─────────────────────────────────────────────────────────────────────────────

def make_conn(fetchall_rows=None, fetchone_row=None):
    """
    Returns (mock_conn, mock_cursor).

    mock_cursor.fetchall() → fetchall_rows  (default [])
    mock_cursor.fetchone() → fetchone_row   (default (1,) — fake activity_id)
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = fetchall_rows if fetchall_rows is not None else []
    mock_cursor.fetchone.return_value = fetchone_row if fetchone_row is not None else (1,)

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_ctx
    return mock_conn, mock_cursor


# ─────────────────────────────────────────────────────────────────────────────
# 1. calc_electricity_emissions  (Scope 2)
# SELECT columns: id, kwh, location, period_start, period_end
# Formula: kWh × grid_factor
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcElectricityEmissions:

    def test_returns_list_of_emission_results(self):
        rows = [(1, 1000.0, "TX", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_electricity_factor", return_value=0.386):
            results = calc_electricity_emissions(conn)

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], EmissionResult)

    def test_correct_emission_math(self):
        # 1000 kWh × 0.386 = 386.0 kg CO₂e
        rows = [(1, 1000.0, "TX", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_electricity_factor", return_value=0.386):
            results = calc_electricity_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(386.0)
        assert results[0].emissions_metric_tons == pytest.approx(0.386)

    def test_scope_is_2(self):
        rows = [(1, 500.0, "CA", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_electricity_factor", return_value=0.25):
            results = calc_electricity_emissions(conn)

        assert results[0].scope == 2

    def test_empty_table_returns_empty_list(self):
        conn, _ = make_conn(fetchall_rows=[])
        results = calc_electricity_emissions(conn)
        assert results == []

    def test_commits_after_processing(self):
        rows = [(1, 100.0, "TX", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_electricity_factor", return_value=0.386):
            calc_electricity_emissions(conn)

        conn.commit.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# 2. calc_stationary_fuel_emissions  (Scope 1)
# SELECT columns: id, fuel_type, quantity, unit, period_start, period_end
# Formula: quantity × fuel_factor
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcStationaryFuelEmissions:

    def test_natural_gas_emission_math(self):
        # 850 therms × 5.302 = 4506.7 kg CO₂e
        rows = [(1, "natural_gas", 850.0, "therms", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_stationary_fuel_factor", return_value=5.302):
            results = calc_stationary_fuel_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(850 * 5.302)

    def test_scope_is_1(self):
        rows = [(1, "propane", 100.0, "gallons", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_stationary_fuel_factor", return_value=5.72):
            results = calc_stationary_fuel_emissions(conn)

        assert results[0].scope == 1

    def test_empty_table_returns_empty_list(self):
        conn, _ = make_conn(fetchall_rows=[])
        results = calc_stationary_fuel_emissions(conn)
        assert results == []

    def test_source_table_label(self):
        rows = [(1, "heating_oil", 200.0, "gallons", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_stationary_fuel_factor", return_value=10.16):
            results = calc_stationary_fuel_emissions(conn)

        assert results[0].source_table == "stationary_fuel"


# ─────────────────────────────────────────────────────────────────────────────
# 3. calc_vehicle_fuel_emissions  (Scope 1)
# SELECT columns: parsed_id, fuel_type, quantity, unit, period_start, period_end
# Formula: quantity × fuel_factor
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcVehicleFuelEmissions:

    def test_gasoline_emission_math(self):
        # 100 gallons × 8.887 = 888.7 kg CO₂e
        rows = [(1, "gasoline", 100.0, "gallon", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_vehicle_fuel_factor", return_value=8.887):
            results = calc_vehicle_fuel_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(888.7)

    def test_diesel_emission_math(self):
        # 200 gallons × 10.21 = 2042.0 kg CO₂e
        rows = [(1, "diesel", 200.0, "gallon", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_vehicle_fuel_factor", return_value=10.21):
            results = calc_vehicle_fuel_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(2042.0)

    def test_scope_is_1(self):
        rows = [(1, "gasoline", 50.0, "gallon", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_vehicle_fuel_factor", return_value=8.887):
            results = calc_vehicle_fuel_emissions(conn)

        assert results[0].scope == 1

    def test_empty_table_returns_empty_list(self):
        conn, _ = make_conn(fetchall_rows=[])
        results = calc_vehicle_fuel_emissions(conn)
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. calc_shipping_emissions  (Scope 3)
# SELECT columns: id, weight_tons, distance_miles, transport_mode, period_start, period_end
# Formula: (weight_tons × distance_miles) × mode_factor
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcShippingEmissions:

    def test_truck_emission_math(self):
        # 0.5 tons × 300 miles = 150 ton-miles × 0.161 = 24.15 kg CO₂e
        rows = [(1, 0.5, 300.0, "truck", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_transport_factor", return_value=0.161):
            results = calc_shipping_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(0.5 * 300 * 0.161)

    def test_air_mode_emission_math(self):
        # 1.0 ton × 100 miles × 2.126 = 212.6 kg CO₂e
        rows = [(1, 1.0, 100.0, "air", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_transport_factor", return_value=2.126):
            results = calc_shipping_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(212.6)

    def test_unknown_mode_falls_back_to_default(self):
        # get_transport_factor should still return a value for unknown mode
        rows = [(1, 1.0, 100.0, "unknown_mode", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_transport_factor", return_value=0.161):
            results = calc_shipping_emissions(conn)

        assert len(results) == 1
        assert results[0].emissions_kg_co2e > 0

    def test_scope_is_3(self):
        rows = [(1, 1.0, 100.0, "truck", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_transport_factor", return_value=0.161):
            results = calc_shipping_emissions(conn)

        assert results[0].scope == 3

    def test_empty_table_returns_empty_list(self):
        conn, _ = make_conn(fetchall_rows=[])
        results = calc_shipping_emissions(conn)
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. calc_waste_emissions  (Scope 3)
# SELECT columns: parsed_id, waste_weight, unit, disposal_method, period_start, period_end
# Formula: waste_kg × disposal_factor
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcWasteEmissions:

    def test_landfill_emission_math(self):
        # 100 kg × 1.9 = 190 kg CO₂e
        rows = [(1, 100.0, "kg", "landfill", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_waste_factor", return_value=1.9), \
             patch("src.calculations.to_kg", return_value=100.0):
            results = calc_waste_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(190.0)

    def test_recycle_produces_zero_emissions(self):
        # recycle factor = 0.0 → 0 kg CO₂e
        rows = [(2, 100.0, "kg", "recycle", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=2), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_waste_factor", return_value=0.0), \
             patch("src.calculations.to_kg", return_value=100.0):
            results = calc_waste_emissions(conn)

        assert results[0].emissions_kg_co2e == pytest.approx(0.0)

    def test_lbs_are_converted_to_kg(self):
        # to_kg must be called with the lb value
        rows = [(3, 220.0, "lbs", "landfill", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=3), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_waste_factor", return_value=1.9), \
             patch("src.calculations.to_kg", return_value=99.79) as mock_to_kg:
            results = calc_waste_emissions(conn)

        mock_to_kg.assert_called_once_with(220.0, "lbs")
        assert results[0].emissions_kg_co2e == pytest.approx(99.79 * 1.9)

    def test_scope_is_3(self):
        rows = [(1, 50.0, "kg", "compost", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity", return_value=1), \
             patch("src.calculations._upsert_emission"), \
             patch("src.calculations.get_waste_factor", return_value=0.1), \
             patch("src.calculations.to_kg", return_value=50.0):
            results = calc_waste_emissions(conn)

        assert results[0].scope == 3


# ─────────────────────────────────────────────────────────────────────────────
# 6. calc_water_metrics  (Non-GHG resource metric)
# SELECT columns: id, water_volume, unit, location, period_start, period_end
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcWaterMetrics:

    def test_gallons_summed_correctly(self):
        rows = [
            (1, 5000.0, "gal", "TX", "2024-01-01", "2024-01-31"),
            (2, 3000.0, "gal", "TX", "2024-01-01", "2024-01-31"),
        ]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity"):
            result = calc_water_metrics(conn)

        assert result["total_water_gallons"] == pytest.approx(8000.0)
        assert result["record_count"] == 2

    def test_m3_converted_to_gallons(self):
        # 1 m³ = 264.172 gallons
        rows = [(1, 1.0, "m3", "CA", "2024-01-01", "2024-01-31")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations._upsert_activity"):
            result = calc_water_metrics(conn)

        assert result["total_water_gallons"] == pytest.approx(264.172)
        assert result["total_water_m3"] == pytest.approx(1.0)

    def test_empty_table_returns_zeros(self):
        conn, _ = make_conn(fetchall_rows=[])
        result = calc_water_metrics(conn)
        assert result["total_water_gallons"] == 0.0
        assert result["record_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. calc_energy_intensity  (Derived metric)
# Formula: total_kWh ÷ denominator_value
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcEnergyIntensity:

    def test_correct_intensity_math(self):
        # 18000 kWh ÷ 25 employees = 720.0 kWh/employee
        conn, mock_cursor = make_conn()
        mock_cursor.fetchone.return_value = (18000.0,)

        result = calc_energy_intensity(
            conn, denominator_type="employees", denominator_value=25
        )

        assert result["energy_intensity_value"] == pytest.approx(720.0)
        assert result["energy_intensity_unit"] == "kWh/employees"
        assert result["total_kwh"] == pytest.approx(18000.0)

    def test_zero_denominator_raises_value_error(self):
        conn, _ = make_conn()
        with pytest.raises(ValueError, match="denominator_value must be > 0"):
            calc_energy_intensity(conn, denominator_type="employees", denominator_value=0)

    def test_negative_denominator_raises_value_error(self):
        conn, _ = make_conn()
        with pytest.raises(ValueError, match="denominator_value must be > 0"):
            calc_energy_intensity(conn, denominator_type="revenue", denominator_value=-1)

    def test_unit_string_contains_denominator_type(self):
        conn, mock_cursor = make_conn()
        mock_cursor.fetchone.return_value = (9000.0,)

        result = calc_energy_intensity(
            conn, denominator_type="shipments", denominator_value=100
        )
        assert "shipments" in result["energy_intensity_unit"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. calc_waste_diversion_rate  (Derived metric)
# SELECT columns: waste_weight, unit, disposal_method
# Formula: (recycled + composted) ÷ total_waste
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcWasteDiversionRate:

    def test_diversion_rate_math(self):
        # 300 recycled + 120 landfill = 420 total → 300/420 ≈ 71.4 %
        rows = [
            (300.0, "kg", "recycle"),
            (120.0, "kg", "landfill"),
        ]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations.to_kg", side_effect=lambda v, u: v):
            result = calc_waste_diversion_rate(conn)

        assert result["diversion_rate"] == pytest.approx(300 / 420, rel=1e-3)
        assert result["diversion_pct"] == pytest.approx((300 / 420) * 100, rel=1e-3)

    def test_all_recycled_gives_100_percent(self):
        rows = [(500.0, "kg", "recycle")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations.to_kg", side_effect=lambda v, u: v):
            result = calc_waste_diversion_rate(conn)

        assert result["diversion_rate"] == pytest.approx(1.0)
        assert result["diversion_pct"] == pytest.approx(100.0)

    def test_all_landfill_gives_zero_percent(self):
        rows = [(500.0, "kg", "landfill")]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations.to_kg", side_effect=lambda v, u: v):
            result = calc_waste_diversion_rate(conn)

        assert result["diversion_rate"] == pytest.approx(0.0)

    def test_empty_table_returns_none_diversion(self):
        conn, _ = make_conn(fetchall_rows=[])
        result = calc_waste_diversion_rate(conn)
        assert result["diversion_rate"] is None
        assert result["diversion_pct"] is None
        assert result["total_waste_kg"] == 0.0

    def test_compost_counts_as_diverted(self):
        rows = [
            (200.0, "kg", "compost"),
            (200.0, "kg", "landfill"),
        ]
        conn, _ = make_conn(fetchall_rows=rows)

        with patch("src.calculations.to_kg", side_effect=lambda v, u: v):
            result = calc_waste_diversion_rate(conn)

        assert result["composted_kg"] == pytest.approx(200.0)
        assert result["diversion_rate"] == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# 9. calc_ghg_summary  (Read-only aggregation across activities + emissions)
# First fetchall → scope rows: (scope, total_kg, total_mt)
# Second fetchall → activity rows: (activity_type, total_kg)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcGhgSummary:

    def _make_conn_with_two_queries(self, scope_rows, activity_rows):
        """cursor.fetchall() returns scope_rows on first call, activity_rows on second."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [scope_rows, activity_rows]

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_cursor)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_ctx
        return mock_conn

    def test_scope_totals_and_grand_total(self):
        scope_rows = [(1, 4000.0, 4.0), (2, 5000.0, 5.0), (3, 1000.0, 1.0)]
        activity_rows = [
            ("vehicle_fuel_use", 4000.0),
            ("purchased_electricity", 5000.0),
            ("waste_generation", 1000.0),
        ]
        conn = self._make_conn_with_two_queries(scope_rows, activity_rows)
        result = calc_ghg_summary(conn)

        assert result["scope1_kg_co2e"] == pytest.approx(4000.0)
        assert result["scope2_kg_co2e"] == pytest.approx(5000.0)
        assert result["scope3_kg_co2e"] == pytest.approx(1000.0)
        assert result["total_kg_co2e"] == pytest.approx(10000.0)
        assert result["total_metric_tons"] == pytest.approx(10.0)

    def test_empty_db_returns_all_zeros(self):
        conn = self._make_conn_with_two_queries([], [])
        result = calc_ghg_summary(conn)

        assert result["total_kg_co2e"] == 0.0
        assert result["total_metric_tons"] == 0.0

    def test_by_activity_type_dict_populated(self):
        scope_rows = [(2, 5000.0, 5.0)]
        activity_rows = [("purchased_electricity", 5000.0)]
        conn = self._make_conn_with_two_queries(scope_rows, activity_rows)
        result = calc_ghg_summary(conn)

        assert "purchased_electricity" in result["by_activity_type"]
        assert result["by_activity_type"]["purchased_electricity"] == pytest.approx(5000.0)