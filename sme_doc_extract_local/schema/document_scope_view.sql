-- document_scope – maps each document to the scope(s) it contributes to.
-- Run after documents.sql (parsed_* tables must exist).
-- scope 0 = water (non-GHG), 1 = direct fuel, 2 = electricity, 3 = shipping/waste.

CREATE OR REPLACE VIEW document_scope AS
  SELECT document_id, 1 AS scope FROM parsed_stationary_fuel
  UNION
  SELECT document_id, 1 AS scope FROM parsed_vehicle_fuel
  UNION
  SELECT document_id, 2 AS scope FROM parsed_electricity
  UNION
  SELECT document_id, 3 AS scope FROM parsed_shipping
  UNION
  SELECT document_id, 3 AS scope FROM parsed_waste
  UNION
  SELECT document_id, 0 AS scope FROM parsed_water;
