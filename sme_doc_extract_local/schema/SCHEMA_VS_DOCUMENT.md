# Schema alignment status

The PostgreSQL schema in [documents.sql](documents.sql) is now **fully aligned** with
**schemaDocument.docx** (SME Sustainability Pulse – Table & Relationship Reference).

---

## What was changed during alignment

| Area | Before alignment | After alignment |
|------|-----------------|-----------------|
| `documents` PK | `id` (BIGSERIAL) | `document_id` (BIGSERIAL) |
| `documents.document_type` | TEXT | VARCHAR(50) |
| `documents.source_filename` | TEXT NOT NULL | VARCHAR(255) nullable |
| Parsed table names | `electricity`, `stationary_fuel`, `shipping`, `water`, `vehicles` | `parsed_electricity`, `parsed_stationary_fuel`, `parsed_shipping`, `parsed_water`, `parsed_vehicle_fuel` |
| Parsed table PKs | `id` (most tables) | `parsed_id` (all parsed_* tables) |
| Cardinality | `UNIQUE(document_id)` on 4 tables — 1:1 per document | No UNIQUE — 1 document → many rows (per doc) |
| Numeric columns | Nullable `NUMERIC` | `NUMERIC(18,4) NOT NULL CHECK (>= 0)` with COALESCE in code |
| Unit/mode columns | `TEXT` without constraints | `VARCHAR(n)` with `CHECK (IN (...))` |
| `created_at` | Missing from electricity, stationary_fuel, shipping, water | Present on all parsed_* tables |
| `parsed_waste` FK | `REFERENCES documents(id)` | `REFERENCES documents(document_id)` |

## No remaining deviations

The schema and code now match schemaDocument.docx exactly.
Activities, emissions, metrics, recommendations, and views were already aligned
and were not changed.
