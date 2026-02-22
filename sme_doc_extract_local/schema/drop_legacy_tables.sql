-- drop_legacy_tables.sql
-- Run this ONCE on databases created before the doc-alignment if you want to
-- remove the old table names and start fresh with the doc-aligned schema.
--
-- WARNING: This permanently deletes all data in the listed tables.
--          Take a backup first if you need to preserve existing rows.
--
-- After running this file, re-apply the schema:
--   cd sme_doc_extract_local && python -m src.main init-db
-- or:
--   psql "$DATABASE_URL" -f sme_doc_extract_local/schema/documents.sql

-- Drop legacy parsed_* tables first (they reference documents)
DROP TABLE IF EXISTS vehicles          CASCADE;
DROP TABLE IF EXISTS water             CASCADE;
DROP TABLE IF EXISTS shipping          CASCADE;
DROP TABLE IF EXISTS stationary_fuel   CASCADE;
DROP TABLE IF EXISTS electricity       CASCADE;

-- Drop documents last (FK source for all of the above).
-- Only needed if you are fully re-creating documents with the new document_id PK.
DROP TABLE IF EXISTS documents         CASCADE;
