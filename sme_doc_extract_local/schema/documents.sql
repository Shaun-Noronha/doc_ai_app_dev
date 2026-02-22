-- PostgreSQL schema for the SME Sustainability Pulse pipeline.
-- Source of truth: schemaDocument.docx (SME Sustainability Pulse – Table & Relationship Reference).
-- All parsed_* tables reference documents(document_id) and allow 1 document → many rows (no UNIQUE on document_id).

-- ─────────────────────────────────────────────────────────────────────────────
-- Core ingestion table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
  document_id    BIGSERIAL PRIMARY KEY,
  document_type  VARCHAR(50) NOT NULL,   -- e.g. 'utility_bill', 'delivery_receipt', 'vehicle_fuel_csv_import'
  exported_json  JSONB NOT NULL,         -- raw OCR / Document AI JSON payload
  source_filename VARCHAR(255),          -- original file name for traceability (nullable)
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- Parsed source tables  (1 document → many rows)
-- ─────────────────────────────────────────────────────────────────────────────

-- parsed_electricity [Scope 2] – electricity consumption from utility bills
CREATE TABLE IF NOT EXISTS parsed_electricity (
  parsed_id      BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  kwh            NUMERIC(18,4) NOT NULL CHECK (kwh >= 0),
  unit           VARCHAR(10) DEFAULT 'kWh',           -- kWh / KWH / kwh
  location       VARCHAR(100),                         -- state or region for grid emission factor lookup
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_electricity_document_id ON parsed_electricity(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_electricity_period ON parsed_electricity(period_start, period_end);

-- parsed_stationary_fuel [Scope 1] – fuel burned in fixed on-site equipment
CREATE TABLE IF NOT EXISTS parsed_stationary_fuel (
  parsed_id      BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  fuel_type      VARCHAR(30) CHECK (fuel_type IN ('natural_gas', 'propane', 'heating_oil')),
  quantity       NUMERIC(18,4) NOT NULL CHECK (quantity >= 0),
  unit           VARCHAR(20) NOT NULL CHECK (unit IN ('therm', 'gallon', 'ft3')),
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_stationary_fuel_document_id ON parsed_stationary_fuel(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_stationary_fuel_period ON parsed_stationary_fuel(period_start, period_end);

-- parsed_vehicle_fuel [Scope 1] – fuel for company-owned or leased vehicles
CREATE TABLE IF NOT EXISTS parsed_vehicle_fuel (
  parsed_id      BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  fuel_type      VARCHAR(20) CHECK (fuel_type IN ('gasoline', 'diesel')),
  quantity       NUMERIC(18,4) NOT NULL CHECK (quantity >= 0),
  unit           VARCHAR(20) CHECK (unit IN ('gallon', 'liter')),
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_vehicle_fuel_document_id ON parsed_vehicle_fuel(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_vehicle_fuel_period ON parsed_vehicle_fuel(period_start, period_end);

-- parsed_shipping [Scope 3] – freight shipment details for transportation emissions
CREATE TABLE IF NOT EXISTS parsed_shipping (
  parsed_id        BIGSERIAL PRIMARY KEY,
  document_id      BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  weight_tons      NUMERIC(18,4) NOT NULL CHECK (weight_tons >= 0),
  distance_miles   NUMERIC(18,4) NOT NULL CHECK (distance_miles >= 0),
  transport_mode   VARCHAR(20) CHECK (transport_mode IN ('truck', 'ship', 'air', 'rail')),
  period_start     DATE,
  period_end       DATE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_shipping_document_id ON parsed_shipping(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_shipping_period ON parsed_shipping(period_start, period_end);

-- parsed_waste [Scope 3] – waste generation records
CREATE TABLE IF NOT EXISTS parsed_waste (
  parsed_id        BIGSERIAL PRIMARY KEY,
  document_id      BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  waste_weight     NUMERIC(18,4) NOT NULL CHECK (waste_weight >= 0),
  unit             VARCHAR(10) NOT NULL CHECK (unit IN ('kg', 'lb')),
  disposal_method  VARCHAR(20) NOT NULL CHECK (disposal_method IN ('landfill', 'recycle', 'compost', 'incinerate')),
  period_start     DATE,
  period_end       DATE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_waste_document_id ON parsed_waste(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_waste_period ON parsed_waste(period_start, period_end);

-- parsed_water [Non-GHG] – water consumption from invoices or meter reads
CREATE TABLE IF NOT EXISTS parsed_water (
  parsed_id      BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  water_volume   NUMERIC(18,4) NOT NULL CHECK (water_volume >= 0),
  unit           VARCHAR(20) CHECK (unit IN ('gallon', 'm3')),
  location       VARCHAR(100),
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parsed_water_document_id ON parsed_water(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_water_period ON parsed_water(period_start, period_end);

-- ─────────────────────────────────────────────────────────────────────────────
-- Activity normalisation and metrics (SME Sustainability Pulse)
-- ─────────────────────────────────────────────────────────────────────────────

-- activities – normalised activity registry (polymorphic link via parsed_table, parsed_id)
CREATE TABLE IF NOT EXISTS activities (
  activity_id    BIGSERIAL PRIMARY KEY,
  parsed_table   VARCHAR(50) NOT NULL,
  parsed_id      BIGINT NOT NULL,
  activity_type  VARCHAR(50) NOT NULL CHECK (activity_type IN (
    'purchased_electricity', 'stationary_fuel_combustion', 'vehicle_fuel_use',
    'transportation_shipping', 'waste_generation', 'water_usage'
  )),
  scope          SMALLINT CHECK (scope IN (1, 2, 3)),   -- NULL for non-GHG activities (e.g. water_usage)
  location       VARCHAR(100),
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (parsed_table, parsed_id)
);

CREATE INDEX IF NOT EXISTS idx_activities_parsed ON activities(parsed_table, parsed_id);
CREATE INDEX IF NOT EXISTS idx_activities_scope ON activities(scope);
CREATE INDEX IF NOT EXISTS idx_activities_period ON activities(period_start, period_end);

-- emissions [Metric 01] – GHG emission calculation results
CREATE TABLE IF NOT EXISTS emissions (
  emission_id            BIGSERIAL PRIMARY KEY,
  activity_id            BIGINT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE UNIQUE,
  emissions_kg_co2e      NUMERIC(18,6) NOT NULL CHECK (emissions_kg_co2e >= 0),
  emissions_metric_tons  NUMERIC(18,6) NOT NULL CHECK (emissions_metric_tons >= 0),
  factor_used            NUMERIC(18,8) NOT NULL,
  factor_unit            VARCHAR(50) NOT NULL,
  calculated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emissions_activity_id ON emissions(activity_id);

-- energy_metrics [Metric 02] – pre-aggregated energy intensity by period
CREATE TABLE IF NOT EXISTS energy_metrics (
  energy_metric_id       BIGSERIAL PRIMARY KEY,
  period_start           DATE NOT NULL,
  period_end             DATE NOT NULL,
  total_kwh              NUMERIC(18,4) NOT NULL CHECK (total_kwh >= 0),
  denominator_type       VARCHAR(50) NOT NULL,
  denominator_value      NUMERIC(18,6) NOT NULL CHECK (denominator_value > 0),
  energy_intensity_value NUMERIC(18,6) NOT NULL CHECK (energy_intensity_value >= 0),
  energy_intensity_unit  VARCHAR(100) NOT NULL,
  created_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_energy_metrics_period ON energy_metrics(period_start, period_end);

-- water_metrics [Metric 03] – aggregated water consumption by period
CREATE TABLE IF NOT EXISTS water_metrics (
  water_metric_id    BIGSERIAL PRIMARY KEY,
  period_start       DATE NOT NULL,
  period_end         DATE NOT NULL,
  total_water_volume NUMERIC(18,4) NOT NULL CHECK (total_water_volume >= 0),
  unit               VARCHAR(20) NOT NULL CHECK (unit IN ('gallon', 'm3')),
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_water_metrics_period ON water_metrics(period_start, period_end);

-- waste_metrics [Metric 03] – aggregated waste and diversion rate by period
CREATE TABLE IF NOT EXISTS waste_metrics (
  waste_metric_id    BIGSERIAL PRIMARY KEY,
  period_start       DATE NOT NULL,
  period_end         DATE NOT NULL,
  total_waste_kg     NUMERIC(18,4) NOT NULL CHECK (total_waste_kg >= 0),
  recycled_waste_kg  NUMERIC(18,4) NOT NULL CHECK (recycled_waste_kg >= 0),
  composted_waste_kg NUMERIC(18,4) NOT NULL CHECK (composted_waste_kg >= 0),
  diversion_rate     NUMERIC(18,6) CHECK (diversion_rate >= 0 AND diversion_rate <= 1),
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waste_metrics_period ON waste_metrics(period_start, period_end);

-- vendors – supplier registry used for sustainability recommendations
CREATE TABLE IF NOT EXISTS vendors (
  vendor_id              VARCHAR(20)  PRIMARY KEY,   -- e.g. V001
  vendor_name            VARCHAR(100) NOT NULL,
  category               VARCHAR(50)  NOT NULL,      -- Packaging, Logistics, Energy Provider, etc.
  product_or_service     VARCHAR(150) NOT NULL,
  carbon_intensity       NUMERIC(10,4) NOT NULL CHECK (carbon_intensity >= 0),  -- kg CO2e per unit
  sustainability_score   SMALLINT NOT NULL CHECK (sustainability_score BETWEEN 0 AND 100),
  distance_km_from_sme   NUMERIC(10,2) CHECK (distance_km_from_sme >= 0),
  created_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vendors_category ON vendors(category);
CREATE INDEX IF NOT EXISTS idx_vendors_sustainability_score ON vendors(sustainability_score DESC);

-- recommendations – free-text suggestions linked to activities
CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id   BIGSERIAL PRIMARY KEY,
  activity_id         BIGINT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
  recommendation_text TEXT NOT NULL,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_activity_id ON recommendations(activity_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Dashboard views (read-only)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW activity_emissions_dashboard AS
SELECT
  a.activity_id,
  a.parsed_table,
  a.parsed_id,
  a.activity_type,
  a.scope,
  a.location,
  a.period_start,
  a.period_end,
  e.emissions_metric_tons,
  e.emissions_kg_co2e,
  e.factor_used,
  e.factor_unit,
  r.recommendation_text
FROM activities a
LEFT JOIN emissions e ON e.activity_id = a.activity_id
LEFT JOIN recommendations r ON r.activity_id = a.activity_id;

CREATE OR REPLACE VIEW ghg_totals_by_scope AS
SELECT
  a.scope,
  COALESCE(SUM(e.emissions_metric_tons), 0) AS total_emissions_metric_tons
FROM activities a
LEFT JOIN emissions e ON e.activity_id = a.activity_id
WHERE a.scope IS NOT NULL
GROUP BY a.scope;
