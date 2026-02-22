# SME Sustainability Pulse

An end-to-end sustainability analytics platform for small and medium enterprises.
The system ingests source documents (invoices, utility bills, shipping receipts),
extracts structured data using Google Document AI and Gemini LLM, calculates
GHG emissions across Scope 1/2/3, and delivers actionable recommendations
through an interactive dashboard.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Setup](#setup)
5. [Running the Application](#running-the-application)
6. [Database Schema](#database-schema)
7. [Recommendation System](#recommendation-system)
8. [API Reference](#api-reference)
9. [Environment Variables](#environment-variables)

---

## Architecture

```
                         Process Flow
                         ============

  PDF / Image / CSV
        |
        v
  [Document AI + Gemini LLM]  -->  Extraction Results (JSON)
        |
        v
  [Classification + Validation]
        |
        v
  [PostgreSQL Database]  <--  Parsed tables (electricity, fuel, shipping, water, waste)
        |
        v
  [Calculations Engine]  -->  Activities, Emissions, Energy/Water/Waste Metrics
        |
        v
  [Recommendation System]  -->  Content-based RS using vendor knowledge base
        |
        v
  [Dashboard API (FastAPI)]  -->  KPIs, Charts, AI Recommendations
        |
        v
  [Dashboard UI (React + Vite)]  -->  Browser at http://localhost:3000
```

---

## Project Structure

```
doc_ai_app_dev/
|
|-- sme_doc_extract_local/       # Document extraction and ingestion pipeline
|   |-- src/
|   |   |-- main.py              # CLI entry point (process, batch, ingest, init-db)
|   |   |-- classify.py          # Heuristic document classifier
|   |   |-- docai_client.py      # Google Document AI API client
|   |   |-- gemini_client.py     # Gemini LLM wrapper with retries
|   |   |-- schemas.py           # Pydantic data models
|   |   |-- db.py                # Database connection and insert utilities
|   |   |-- calculations.py      # Emission and metric calculation engine
|   |   |-- emission_factors.py  # EPA emission factor constants
|   |   |-- constants.py         # Labels, thresholds, keyword patterns
|   |   |-- validators.py        # Validation and normalisation rules
|   |   |-- io_utils.py          # File I/O helpers
|   |   |-- config.py            # Environment variable loading
|   |   |-- vehicleDataIngest.py # CSV import for vehicle fuel data
|   |   +-- extractors/          # Per-document-type extraction logic
|   |       |-- invoice_extractor.py
|   |       |-- utility_extractor.py
|   |       +-- logistics_extractor.py
|   |-- schema/
|   |   |-- documents.sql        # Full PostgreSQL schema
|   |   +-- README.md            # Schema documentation
|   |-- samples/                 # Sample input documents
|   |-- out/                     # Extraction output directory
|   |-- run_calculations.py      # Standalone calculation runner
|   |-- seed_vendors.py          # Vendor knowledge base seeder
|   |-- seed_synthetic_data.py   # Synthetic test data generator
|   |-- tests/                   # Unit tests
|   +-- requirements.txt
|
|-- dashboard_api/               # FastAPI backend for the dashboard
|   |-- main.py                  # API routes and application setup
|   |-- queries.py               # SQL aggregation queries and snapshot caching
|   |-- recommendations.py       # Content-based recommendation system
|   |-- emission_factors.py      # Emission factors for inline SQL calculations
|   |-- db.py                    # Database connection helper
|   +-- requirements.txt
|
|-- dashboard/                   # React + TypeScript frontend
|   |-- src/
|   |   |-- App.tsx              # Root application component
|   |   |-- api.ts               # API client (proxied to FastAPI backend)
|   |   |-- types.ts             # TypeScript type definitions
|   |   |-- views/
|   |   |   +-- Dashboard.tsx    # Main dashboard view
|   |   |-- components/
|   |   |   |-- KpiCard.tsx      # KPI metric cards
|   |   |   |-- ScopeDonut.tsx   # Emissions by scope (doughnut chart)
|   |   |   |-- SourceBarChart.tsx
|   |   |   |-- RecommendationCard.tsx
|   |   |   |-- SparklineChart.tsx
|   |   |   |-- ProgressRing.tsx
|   |   |   +-- Sidebar.tsx
|   |   +-- hooks/
|   |       +-- useDashboard.ts  # Data fetching hook
|   |-- index.html
|   |-- vite.config.ts           # Vite config with API proxy to port 8000
|   +-- package.json
|
|-- docker-compose.yml
|-- dockerFile
|-- .env                         # Environment variables (not committed)
+-- .gitignore
```

---

## Prerequisites

| Requirement       | Version       |
|-------------------|---------------|
| Python            | 3.10 or later |
| Node.js           | 18 or later   |
| PostgreSQL        | 14 or later   |
| Google Cloud project | Billing enabled, Document AI API enabled |
| Gemini API key    | From Google AI Studio |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Shaun-Noronha/doc_ai_app_dev.git
cd doc_ai_app_dev
```

### 2. Create and configure the environment file

```bash
cp .env.example .env
# Edit .env with your DATABASE_URL, Google Cloud credentials, and Gemini API key
```

### 3. Set up the Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate.bat    # Windows CMD
# .venv\Scripts\Activate.ps1    # Windows PowerShell
```

### 4. Install Python dependencies

```bash
pip install -r sme_doc_extract_local/requirements.txt
pip install -r dashboard_api/requirements.txt
```

### 5. Initialise the database schema

```bash
cd sme_doc_extract_local
python -m src.main init-db
cd ..
```

### 6. Seed the vendor knowledge base

```bash
cd sme_doc_extract_local
python seed_vendors.py
cd ..
```

### 7. Install frontend dependencies

```bash
cd dashboard
npm install
cd ..
```

---

## Running the Application

### Document extraction pipeline

```bash
cd sme_doc_extract_local

# Process a single document
python -m src.main process --file "samples/invoice1.png"

# Process all documents in a directory
python -m src.main batch --dir "samples/"

# Ingest extracted data into the database
python -m src.main ingest --dir "out/"
```

### Run emission calculations

```bash
cd sme_doc_extract_local
python run_calculations.py
```

### Start the dashboard API (port 8000)

```bash
# From the project root
source .venv/bin/activate
uvicorn dashboard_api.main:app --reload --port 8000
```

### Generate recommendations

With the API server running, trigger the recommendation engine:

```bash
curl -X POST http://localhost:8000/recommendations/generate
```

### Refresh the dashboard snapshot

```bash
curl -X POST http://localhost:8000/api/refresh
```

### Start the frontend (port 3000)

```bash
cd dashboard
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Database Schema

The PostgreSQL database contains the following table groups.

### Parsed source tables (populated by the extraction pipeline)

| Table                  | Scope   | Content                          |
|------------------------|---------|----------------------------------|
| documents              |         | One row per ingested file        |
| parsed_electricity     | Scope 2 | Electricity consumption (kWh)    |
| parsed_stationary_fuel | Scope 1 | On-site fuel combustion          |
| parsed_vehicle_fuel    | Scope 1 | Company vehicle fuel usage       |
| parsed_shipping        | Scope 3 | Freight shipment records         |
| parsed_waste           | Scope 3 | Waste generation records         |
| parsed_water           | Non-GHG | Water consumption                |

### Computed tables (populated by calculations and the recommendation engine)

| Table            | Content                                       |
|------------------|-----------------------------------------------|
| activities       | Normalised activity registry linked to sources|
| emissions        | GHG calculation results per activity          |
| energy_metrics   | Aggregated energy intensity by period         |
| water_metrics    | Aggregated water consumption by period        |
| waste_metrics    | Aggregated waste and diversion rates          |
| recommendations  | AI-generated sustainability recommendations   |
| vendors          | Vendor knowledge base with sustainability profiles |
| dashboard_snapshot | Cached dashboard payload for fast reads     |

For full schema details, see `sme_doc_extract_local/schema/README.md`.

---

## Recommendation System

The dashboard includes a content-based recommendation system that evaluates
sustainability data against three criteria.

### Criteria

**1. Better Closer Hauler**

Matches each shipping record group against Logistics vendors in the
`vendors` table. For each vendor that is geographically closer than the
current shipping distance, the system computes the CO2e saving and scores
the recommendation using the vendor's sustainability rating.

**2. Alternative Material**

Compares vendors within the same category (Packaging, Raw Materials,
Office Supplies, Energy) using cosine similarity on vendor profile vectors
[1/carbon_intensity, sustainability_score, 1/distance]. Within each
category, identifies the highest-carbon vendor and recommends switching
to the greenest alternative based on a weighted score of emission reduction,
sustainability rating, and profile similarity.

**3. Change Shipment Method**

For each shipping record group, computes emissions under every viable
transport mode (truck, rail, ship, air) using EPA ton-mile emission factors.
Recommends the mode switch that yields the highest saving, weighted by
a feasibility factor (rail: 0.70, ship: 0.50, truck/air: 0.95).

### Pipeline

1. Load vendor profiles and shipping records from the database.
2. Group identical records by fingerprint to eliminate duplicates.
3. Generate candidate recommendations for each group and applicable criterion.
4. Normalise all candidate scores to [0, 1] using MinMaxScaler.
5. Apply Maximal Marginal Relevance (MMR) reranking per criterion using
   cosine similarity on feature vectors to ensure diversity.
6. Persist the top recommendations and refresh the dashboard snapshot.

### Fallback behaviour

When no data is available in the database, the dashboard displays a
single placeholder card indicating that no data was found.

---

## API Reference

### Dashboard endpoints

| Method | Path                    | Description                            |
|--------|-------------------------|----------------------------------------|
| GET    | /api/dashboard          | Full cached dashboard payload          |
| POST   | /api/refresh            | Rebuild the dashboard snapshot         |
| GET    | /api/kpis               | Top-level KPI metrics                  |
| GET    | /api/emissions-by-scope | Emissions split by Scope 1/2/3         |
| GET    | /api/emissions-by-source| Emissions split by source category     |
| GET    | /api/recommendations    | AI recommendations (from snapshot)     |
| GET    | /health                 | Health check                           |

### Recommendation endpoints

| Method | Path                       | Description                         |
|--------|----------------------------|-------------------------------------|
| POST   | /recommendations/generate  | Run the full recommendation pipeline|
| GET    | /recommendations           | Fetch scored recommendations        |
| GET    | /recommendations?criteria= | Filter by: better_closer_hauler, alternative_material, change_shipment_method |

---

## Environment Variables

| Variable                         | Required | Description                          |
|----------------------------------|----------|--------------------------------------|
| DATABASE_URL                     | Yes      | PostgreSQL connection string         |
| GOOGLE_APPLICATION_CREDENTIALS   | Yes      | Path to GCP service account JSON key |
| GOOGLE_CLOUD_PROJECT             | Yes      | Google Cloud project ID              |
| DOCAI_LOCATION                   | Yes      | Document AI region (us or eu)        |
| DOCAI_INVOICE_PROCESSOR_ID       | Yes      | Document AI invoice processor ID     |
| DOCAI_RECEIPT_PROCESSOR_ID       | Yes      | Document AI receipt processor ID     |
| DOCAI_FORM_PROCESSOR_ID          | Yes      | Document AI form processor ID        |
| GEMINI_API_KEY                   | Yes      | Gemini API key from AI Studio        |

---

## License

This project was built for the HerHacks hackathon.
