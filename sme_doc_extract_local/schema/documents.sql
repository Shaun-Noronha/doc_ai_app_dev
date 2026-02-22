-- PostgreSQL schema for document extraction output.
-- One documents table + four category tables (electricity, stationary_fuel, shipping, water).

-- One row per ingested document. exported_json = full extraction.json payload.
CREATE TABLE documents (
  id                BIGSERIAL PRIMARY KEY,
  document_type     TEXT NOT NULL,       -- e.g. 'utility_bill', 'invoice', 'delivery_receipt'
  source_filename   TEXT NOT NULL,       -- original file path or name
  exported_json     JSONB NOT NULL,      -- full extraction payload (source_file, doc_type, extraction, confidence, warnings, created_at)
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Electricity: from utility_bill with utility_type = 'electricity'
CREATE TABLE electricity (
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
CREATE TABLE stationary_fuel (
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
CREATE TABLE shipping (
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
CREATE TABLE water (
  id            BIGSERIAL PRIMARY KEY,
  document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  water_volume  NUMERIC,
  unit         TEXT,                    -- e.g. 'gal', 'm³'
  location     TEXT,
  period_start DATE,
  period_end   DATE,
  UNIQUE(document_id)
);

-- Optional indexes for filtering by document_type and by period
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_electricity_period ON electricity(period_start, period_end);
CREATE INDEX idx_stationary_fuel_period ON stationary_fuel(period_start, period_end);
CREATE INDEX idx_shipping_period ON shipping(period_start, period_end);
CREATE INDEX idx_water_period ON water(period_start, period_end);
