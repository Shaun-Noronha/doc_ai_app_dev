-- selected_vendors – records which vendors are selected from the frontend.
-- Run after documents.sql (vendors table must exist).
-- One row per selected vendor; replacing selection = delete all then insert new set.

CREATE TABLE IF NOT EXISTS selected_vendors (
  vendor_id   VARCHAR(20) PRIMARY KEY REFERENCES vendors(vendor_id) ON DELETE CASCADE,
  selected_at TIMESTAMPTZ DEFAULT NOW()
);
