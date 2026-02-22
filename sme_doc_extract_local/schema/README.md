# PostgreSQL schema for document extraction

This directory holds the database schema for the SME Sustainability Pulse pipeline.
The schema is fully aligned with **schemaDocument.docx** (SME Sustainability Pulse – Table & Relationship Reference).

Apply the schema with:

```bash
# from the project root
cd sme_doc_extract_local && python -m src.main init-db
# or directly with psql
psql "$DATABASE_URL" -f sme_doc_extract_local/schema/documents.sql
```

---

## Tables

### Core ingestion

| Table | PK | Purpose |
|-------|----|---------|
| **documents** | `document_id` | One row per ingested file: `document_type`, `source_filename` (nullable), `exported_json` (full payload), `created_at`. |

### Parsed source tables (1 document → many rows)

All `parsed_*` tables reference `documents(document_id)` via FK with `ON DELETE CASCADE`. There is **no** `UNIQUE(document_id)` constraint — one document can yield multiple rows.

| Table | Scope | Purpose |
|-------|-------|---------|
| **parsed_electricity** | Scope 2 | Electricity consumption: `kwh` (NOT NULL ≥ 0), `unit` DEFAULT 'kWh', `location`, period. |
| **parsed_stationary_fuel** | Scope 1 | Fixed on-site fuel: `fuel_type` (natural_gas \| propane \| heating_oil), `quantity` (NOT NULL ≥ 0), `unit` (therm \| gallon \| ft3, NOT NULL), period. |
| **parsed_vehicle_fuel** | Scope 1 | Company vehicle fuel: `fuel_type` (gasoline \| diesel), `quantity` (NOT NULL ≥ 0), `unit` (gallon \| liter), period. |
| **parsed_shipping** | Scope 3 | Freight shipments: `weight_tons` and `distance_miles` (both NOT NULL ≥ 0), `transport_mode` (truck \| ship \| air \| rail), period. |
| **parsed_waste** | Scope 3 | Waste records: `waste_weight` (NOT NULL ≥ 0), `unit` (kg \| lb, NOT NULL), `disposal_method` (landfill \| recycle \| compost \| incinerate, NOT NULL), period. |
| **parsed_water** | Non-GHG | Water consumption: `water_volume` (NOT NULL ≥ 0), `unit` (gallon \| m3), `location`, period. |

### Activity normalisation and metrics

| Table | Purpose |
|-------|---------|
| **activities** | Normalised activity registry. Links back to source row via polymorphic `(parsed_table, parsed_id)`. `scope` = 1, 2, or 3; NULL for non-GHG activities (e.g. water). |
| **emissions** | GHG results per activity: `emissions_kg_co2e`, `emissions_metric_tons`, `factor_used`, `factor_unit`. UNIQUE on `activity_id` (one emission per activity). |
| **energy_metrics** | Pre-aggregated energy intensity by period: `total_kwh`, `denominator_type`, `denominator_value`, `energy_intensity_value/unit` (Metric 02). |
| **water_metrics** | Aggregated water volume by period: `total_water_volume`, `unit` (gallon \| m3) (Metric 03). |
| **waste_metrics** | Aggregated waste and diversion rate: `total_waste_kg`, `recycled_waste_kg`, `composted_waste_kg`, `diversion_rate` (Metric 03). |
| **recommendations** | Free-text suggestions linked to activities. One activity can have many recommendations. |

## Views

| View | Source tables | Purpose |
|------|--------------|---------|
| **activity_emissions_dashboard** | activities, emissions, recommendations | Unified join for the main dashboard: activity type, scope, period, emissions, recommendation text. |
| **ghg_totals_by_scope** | activities, emissions | Sum of `emissions_metric_tons` grouped by GHG scope (Scope 1/2/3 breakdown charts). |

---

## Data flow

```
documents
  └── parsed_electricity   → activities → emissions
  └── parsed_stationary_fuel → activities → emissions
  └── parsed_vehicle_fuel  → activities → emissions
  └── parsed_shipping      → activities → emissions
  └── parsed_waste         → activities → emissions
  └── parsed_water         → activities   (no emissions; water_usage is non-GHG)
                                         ↳ recommendations (many per activity)

Scheduled aggregation:
  parsed_electricity  → energy_metrics
  parsed_water        → water_metrics
  parsed_waste        → waste_metrics
```

---

## Extraction → table mapping

| Source | Target table | Key mappings |
|--------|-------------|--------------|
| `utility_bill` + `utility_type=electricity` | parsed_electricity | `electricity_kwh` → kwh; `location` → location; `billing_period_*` → period_start/end |
| `utility_bill` + `utility_type=gas` | parsed_stationary_fuel | `natural_gas_therms` → quantity; unit = `therm`; `billing_period_*` → period_start/end |
| `utility_bill` + `utility_type=water` | parsed_water | `water_volume` → water_volume; `water_unit` → unit; `location` → location |
| `delivery_receipt` / logistics | parsed_shipping | `weight_kg / 1000` → weight_tons; `distance_km × 0.621371` → distance_miles; `mode` → transport_mode |
| CSV (`vehicleDataIngest`) | parsed_vehicle_fuel | fuel_type normalised to gasoline/diesel; unit to gallon/liter; one synthetic `documents` row per CSV import run |

---

## Migrating from the legacy schema

If your database was created before the doc-alignment (it has tables `documents` with `id` PK, `electricity`, `stationary_fuel`, `shipping`, `water`, `vehicles`), drop them before re-running `init-db`:

```bash
psql "$DATABASE_URL" -f sme_doc_extract_local/schema/drop_legacy_tables.sql
cd sme_doc_extract_local && python -m src.main init-db
```

See [drop_legacy_tables.sql](drop_legacy_tables.sql) for the exact statements.
