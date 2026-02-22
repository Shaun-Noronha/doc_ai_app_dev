# PostgreSQL schema for document extraction

This directory holds the database schema for persisting output from the SME document extraction pipeline (`out/*/extraction.json`). The full relational design (including activities, emissions, and metrics) follows **schemaDocument.docx** (SME Sustainability Pulse – Table & Relationship Reference).

## Tables

| Table | Purpose |
|-------|---------|
| **documents** | One row per processed file: `document_type`, `source_filename`, full `exported_json` (JSONB). |
| **electricity** | Parsed electricity bills: kwh, unit, location, period_start, period_end. |
| **stationary_fuel** | Gas utility bills: fuel_type, quantity, unit, period_start, period_end. |
| **shipping** | Logistics/delivery docs: weight_tons, distance_miles, transport_mode, period_start, period_end. |
| **water** | Water bills: water_volume, unit, location, period_start, period_end. |
| **vehicles** | Vehicle fuel consumption: fuel_type, quantity, unit, period_start, period_end (FK → documents). |
| **parsed_waste** | Waste records: waste_weight, unit, disposal_method, period (Scope 3). |
| **activities** | Normalised activity registry; polymorphic link to parsed_* via (parsed_table, parsed_id). |
| **emissions** | GHG results per activity: emissions_kg_co2e, emissions_metric_tons, factor_used (Metric 01). |
| **energy_metrics** | Pre-aggregated energy intensity by period (Metric 02). |
| **water_metrics** | Pre-aggregated water volume by period (Metric 03). |
| **waste_metrics** | Pre-aggregated waste and diversion rate by period (Metric 03). |
| **recommendations** | Free-text suggestions linked to activities. |

Category tables reference `documents(id)` via `document_id`. Each document can have at most one row in each category table (`UNIQUE(document_id)`).

## Views

| View | Purpose |
|------|---------|
| **activity_emissions_dashboard** | Join of activities, emissions, and recommendations for dashboard queries. |
| **ghg_totals_by_scope** | Sum of emissions_metric_tons grouped by scope (Scope 1/2/3 breakdown). |

## Extraction → table mapping

- **documents**: `document_type` ← `doc_type`; `source_filename` ← `source_file` (path or basename); `exported_json` ← full extraction payload.
- **electricity**: `kwh` ← `extraction.electricity_kwh`; `unit` ← `'kWh'`; `location` ← `extraction.location`; `period_start`/`period_end` ← `extraction.billing_period_start`/`billing_period_end`. Populate when `doc_type` = `utility_bill` and `extraction.utility_type` = `electricity`.
- **stationary_fuel**: `fuel_type` ← `'natural_gas'`; `quantity` ← `extraction.natural_gas_therms`; `unit` ← `'therms'`; periods from `billing_period_*`. Populate when `utility_type` = `gas`.
- **shipping**: `weight_tons` ← `extraction.weight_kg / 1000`; `distance_miles` ← `extraction.distance_km * 0.621371`; `transport_mode` ← `extraction.mode`; `period_start` from `extraction.date` (period_end optional). Populate for logistics/delivery_receipt documents.
- **water**: `water_volume`, `unit`, `location`, `period_start`/`period_end` from utility extraction when `utility_type` = `water`. The pipeline does not yet extract `water_volume`; add it to the utility extractor/schema to fill this table, or backfill from `exported_json` later.

## Applying the schema

```bash
psql -U your_user -d your_db -f schema/documents.sql
```

Or from the project root:

```bash
psql "$DATABASE_URL" -f sme_doc_extract_local/schema/documents.sql
```

Ingestion (reading `extraction.json` and inserting into these tables) is not part of this repo; implement separately (e.g. Python script or API).
