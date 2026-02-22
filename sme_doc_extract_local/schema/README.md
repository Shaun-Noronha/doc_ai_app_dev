# PostgreSQL schema for document extraction

This directory holds the database schema for persisting output from the SME document extraction pipeline (`out/*/extraction.json`).

## Tables

| Table | Purpose |
|-------|---------|
| **documents** | One row per processed file: `document_type`, `source_filename`, full `exported_json` (JSONB). |
| **electricity** | Parsed electricity bills: kwh, unit, location, period_start, period_end. |
| **stationary_fuel** | Gas utility bills: fuel_type, quantity, unit, period_start, period_end. |
| **shipping** | Logistics/delivery docs: weight_tons, distance_miles, transport_mode, period_start, period_end. |
| **water** | Water bills: water_volume, unit, location, period_start, period_end. |

Category tables reference `documents(id)` via `document_id`. Each document can have at most one row in each category table (`UNIQUE(document_id)`).

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
