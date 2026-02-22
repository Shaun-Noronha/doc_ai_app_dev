-- PostgreSQL schema for document extraction output.
-- One documents table + four category tables (electricity, stationary_fuel, shipping, water).

-- One row per ingested document. exported_json = full extraction.json payload.
CREATE TABLE IF NOT EXISTS documents (
  id                BIGSERIAL PRIMARY KEY,
  document_type     TEXT NOT NULL,       -- e.g. 'utility_bill', 'invoice', 'delivery_receipt'
  source_filename   TEXT NOT NULL,       -- original file path or name
  exported_json     JSONB NOT NULL,      -- full extraction payload (source_file, doc_type, extraction, confidence, warnings, created_at)
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Electricity: from utility_bill with utility_type = 'electricity'
CREATE TABLE IF NOT EXISTS electricity (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  kwh          NUMERIC,
  unit         TEXT,                    -- e.g. 'kWh'
  location     TEXT,                    -- city, state
  period_start DATE,
  period_end   DATE,
  UNIQUE(document_id)
);

-- Stationary fuel (gas utility): from utility_bill with utility_type = 'gas'
CREATE TABLE IF NOT EXISTS stationary_fuel (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  fuel_type     TEXT,                   -- e.g. 'natural_gas'
  quantity      NUMERIC,
  unit         TEXT,                    -- e.g. 'therms'
  period_start DATE,
  period_end   DATE,
  UNIQUE(document_id)
);

-- Shipping: from delivery_receipt / logistics extraction
CREATE TABLE IF NOT EXISTS shipping (
  id              BIGSERIAL PRIMARY KEY,
  document_id     BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  weight_tons     NUMERIC,               -- convert from weight_kg: divide by 1000
  distance_miles  NUMERIC,               -- convert from distance_km: multiply by 0.621371
  transport_mode  TEXT,                  -- truck, air, sea, rail
  period_start    DATE,                  -- from logistics "date" or leave null
  period_end      DATE,
  UNIQUE(document_id)
);

-- Water: from utility_bill with utility_type = 'water'
CREATE TABLE IF NOT EXISTS water (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  water_volume  NUMERIC,
  unit         TEXT,                    -- e.g. 'gal', 'm³'
  location     TEXT,
  period_start DATE,
  period_end   DATE,
  UNIQUE(document_id)
);

-- Vehicles: fuel consumption linked to a source document
CREATE TABLE IF NOT EXISTS vehicles (
  parsed_id     BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  fuel_type     VARCHAR(20) NOT NULL CHECK (fuel_type IN ('gasoline', 'diesel')),
  quantity      NUMERIC(18,4) NOT NULL CHECK (quantity >= 0),
  unit          VARCHAR(20) NOT NULL CHECK (unit IN ('gallon', 'liter')),
  period_start  DATE,
  period_end    DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Optional indexes for filtering by document_type and by period
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_electricity_period ON electricity(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_stationary_fuel_period ON stationary_fuel(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_shipping_period ON shipping(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_water_period ON water(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_vehicles_document_id ON vehicles(document_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_period ON vehicles(period_start, period_end);

-- ─────────────────────────────────────────────────────────────────────────────
-- SME Sustainability Pulse – additional tables and views (schemaDocument.docx)
-- ─────────────────────────────────────────────────────────────────────────────

-- parsed_waste [Scope 3] – waste generation records
CREATE TABLE IF NOT EXISTS parsed_waste (
  parsed_id       BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  waste_weight   NUMERIC(18,4) NOT NULL CHECK (waste_weight >= 0),
  unit           VARCHAR(10) NOT NULL CHECK (unit IN ('kg', 'lb')),
  disposal_method VARCHAR(20) NOT NULL CHECK (disposal_method IN ('landfill', 'recycle', 'compost', 'incinerate')),
  period_start   DATE,
  period_end     DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_parsed_waste_document_id ON parsed_waste(document_id);
CREATE INDEX IF NOT EXISTS idx_parsed_waste_period ON parsed_waste(period_start, period_end);

-- activities – normalised activity registry (polymorphic link via parsed_table, parsed_id)
CREATE TABLE IF NOT EXISTS activities (
  activity_id    BIGSERIAL PRIMARY KEY,
  parsed_table   VARCHAR(50) NOT NULL,
  parsed_id      BIGINT NOT NULL,
  activity_type  VARCHAR(50) NOT NULL CHECK (activity_type IN (
    'purchased_electricity', 'stationary_fuel_combustion', 'vehicle_fuel_use',
    'transportation_shipping', 'waste_generation', 'water_usage'
  )),
  scope         SMALLINT CHECK (scope IN (1, 2, 3)),
  location      VARCHAR(100),
  period_start  DATE,
  period_end    DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activities_parsed ON activities(parsed_table, parsed_id);
CREATE INDEX IF NOT EXISTS idx_activities_scope ON activities(scope);
CREATE INDEX IF NOT EXISTS idx_activities_period ON activities(period_start, period_end);

-- emissions [Metric 01] – GHG emission calculation results
CREATE TABLE IF NOT EXISTS emissions (
  emission_id         BIGSERIAL PRIMARY KEY,
  activity_id         BIGINT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE UNIQUE,
  emissions_kg_co2e    NUMERIC(18,6) NOT NULL CHECK (emissions_kg_co2e >= 0),
  emissions_metric_tons NUMERIC(18,6) NOT NULL CHECK (emissions_metric_tons >= 0),
  factor_used         NUMERIC(18,8) NOT NULL,
  factor_unit         VARCHAR(50) NOT NULL,
  calculated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_emissions_activity_id ON emissions(activity_id);

-- energy_metrics [Metric 02] – pre-aggregated energy intensity
CREATE TABLE IF NOT EXISTS energy_metrics (
  energy_metric_id      BIGSERIAL PRIMARY KEY,
  period_start          DATE NOT NULL,
  period_end            DATE NOT NULL,
  total_kwh             NUMERIC(18,4) NOT NULL CHECK (total_kwh >= 0),
  denominator_type      VARCHAR(50) NOT NULL,
  denominator_value     NUMERIC(18,6) NOT NULL CHECK (denominator_value > 0),
  energy_intensity_value NUMERIC(18,6) NOT NULL CHECK (energy_intensity_value >= 0),
  energy_intensity_unit VARCHAR(100) NOT NULL,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_energy_metrics_period ON energy_metrics(period_start, period_end);

-- water_metrics [Metric 03] – aggregated water consumption by period
CREATE TABLE IF NOT EXISTS water_metrics (
  water_metric_id   BIGSERIAL PRIMARY KEY,
  period_start      DATE NOT NULL,
  period_end        DATE NOT NULL,
  total_water_volume NUMERIC(18,4) NOT NULL CHECK (total_water_volume >= 0),
  unit              VARCHAR(20) NOT NULL CHECK (unit IN ('gallon', 'm3')),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_water_metrics_period ON water_metrics(period_start, period_end);

-- waste_metrics [Metric 03] – aggregated waste and diversion rate
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

-- recommendations – free-text suggestions linked to activities
CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id   BIGSERIAL PRIMARY KEY,
  activity_id         BIGINT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
  recommendation_text TEXT NOT NULL,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recommendations_activity_id ON recommendations(activity_id);

-- Dashboard views (read-only)
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
