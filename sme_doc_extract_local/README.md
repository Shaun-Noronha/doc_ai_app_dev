# SME Document Extraction – Local CLI Pipeline

A small-scale, local CLI tool that ingests PDF documents (invoices, utility bills, logistics reports),
runs **Google Cloud Document AI** for OCR / layout extraction, then uses **Gemini LLM** to extract
structured JSON and validates the results.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Google Cloud – Document AI setup](#google-cloud--document-ai-setup)
4. [Google AI Studio – Gemini API key](#google-ai-studio--gemini-api-key)
5. [Local environment setup](#local-environment-setup)
6. [Configuration (.env)](#configuration-env)
7. [Running the tool](#running-the-tool)
8. [Output format](#output-format)
9. [Troubleshooting](#troubleshooting)

---

## Architecture overview

```
PDF or image file
  │
  ▼
[Document AI]  →  raw text + optional entities/tables (OCR for images)
  │
  ▼
[Classifier]   →  invoice | receipt | delivery_receipt | utility_bill | unknown
  │
  ▼
[Gemini LLM]   →  structured JSON (schema-specific prompt)
  │
  ▼
[Validator]    →  normalised fields, warnings, confidence scores
  │
  ▼
out/<stem>/
  ├── raw_text.txt
  ├── extraction.json
  ├── warnings.json
  ├── meta.json
  └── docai.json   (always included)
```

---

## Supported file types

- **PDF** (text-based or scanned)
- **Images** (JPEG, PNG, GIF, BMP, WebP, TIFF)

Document AI performs OCR automatically on all file types.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or later |
| Google Cloud project | Billing enabled |
| Document AI API | Enabled in your project |
| Gemini API key | From Google AI Studio |

---

## Google Cloud – Document AI setup

### 1. Enable the API

```
https://console.cloud.google.com/apis/library/documentai.googleapis.com
```

Click **Enable** for your project.

### 2. Create processors

1. Go to **Document AI → My Processors → Create Processor**.
2. Create these processors (names shown match the requested mapping):
  - **herHacksInvoiceProcessor** → use **Invoice Parser**
  - **herHacksReceiptProcessor** → use **Receipt Parser** (or general OCR if unavailable)
  - **herHacksFormProcessor** → use **Document OCR** (general OCR)
3. Choose a region – **us** or **eu** (must match `DOCAI_LOCATION` in your `.env`).
4. After creation, copy each **Processor ID** from its detail page.

### 3. Create a service account and download the key

1. Go to **IAM & Admin → Service Accounts → Create Service Account**.
2. Grant the role **Document AI API User** (`roles/documentai.apiUser`).
3. Click **Keys → Add Key → JSON**. Save the downloaded file somewhere safe.
4. Set `GOOGLE_APPLICATION_CREDENTIALS` in your `.env` to the **full path** of that JSON file.

---

## Google AI Studio – Gemini API key

1. Visit [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Click **Create API Key** and copy the value.
3. Set `GEMINI_API_KEY` in your `.env`.

---

## Local environment setup

```bash
# 1. Clone / navigate to the repo
cd sme_doc_extract_local

# 2. Create a virtual environment (Python 3.10+)
python -m venv .venv

# 3. Activate it
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

---

## Configuration (.env)

Copy the example file and fill in your values:

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env`:

```dotenv
# Path to your downloaded service-account JSON key
GOOGLE_APPLICATION_CREDENTIALS=C:/Users/you/keys/service-account.json

# Your GCP project ID
GOOGLE_CLOUD_PROJECT=my-gcp-project-id

# Document AI processor location (must match where you created the processors)
DOCAI_LOCATION=us

# Processor IDs from the Document AI console
DOCAI_INVOICE_PROCESSOR_ID=invoice-processor-id
DOCAI_RECEIPT_PROCESSOR_ID=receipt-processor-id
DOCAI_FORM_PROCESSOR_ID=form-processor-id

# Gemini API key from Google AI Studio
GEMINI_API_KEY=AIza...
```

> **Windows note**: Use forward slashes `/` or double back-slashes `\\` in paths.

---

## Running the tool

### Process a single file

```bash
# PDF
python -m src.main process --file "samples/invoice1.pdf"

# Image
python -m src.main process --file "samples/receipt.jpg"
```

With all options:

```bash
python -m src.main process \
  --file "samples/invoice1.pdf" \
  --outdir "out" \
  --doc-type invoice \
  --max-pages 5 \
  --gemini-model "gemini-2.5-flash" \
  --verbose
```

### Process an entire directory (all PDFs and images)

```bash
python -m src.main batch --dir "samples/"
```

With options:

```bash
python -m src.main batch \
  --dir "samples/" \
  --outdir "out" \
  --doc-type auto \
  --verbose
```

### CLI options reference

| Flag | Default | Description |
|------|---------|-------------|
| `--file FILE` | – | (process) Path to a single PDF or image |
| `--dir DIR` | – | (batch) Directory with PDF/image files |
| `--outdir DIR` | `out` | Root output directory |
| `--doc-type TYPE` | `auto` | `invoice` / `receipt` / `delivery_receipt` / `utility_bill` / `utility` / `logistics` / `auto` |
| `--max-pages N` | all | Limit Document AI to first N pages (PDFs only) |
| `--gemini-model MODEL` | `gemini-2.5-flash` | Gemini model name |
| `--verbose` | off | Print step-by-step progress |

---

## Output format

Each processed PDF produces a sub-directory under `out/`:

```
out/
└── invoice1/
    ├── raw_text.txt        ← Plain text from Document AI
    ├── extraction.json     ← Final structured JSON + confidence + warnings
    ├── warnings.json       ← Standalone warning list
    ├── meta.json           ← Timings, model, page count, status
    └── docai.json          ← Raw Document AI response (always included)
```

### extraction.json structure

```json
{
  "source_file": "samples/invoice1.pdf",
  "doc_type": "invoice",
  "extraction_method": "document_ai + gemini",
  "extraction": {
    "vendor_name": "Acme Corp",
    "invoice_number": "INV-2024-001",
    "invoice_date": "2024-03-15",
    "due_date": "2024-04-15",
    "currency": "USD",
    "subtotal": 1000.00,
    "tax": 80.00,
    "total": 1080.00,
    "line_items": [
      {
        "description": "Widget A",
        "quantity": 10,
        "unit_price": 100.00,
        "total_price": 1000.00
      }
    ]
  },
  "confidence": {
    "vendor_name": 0.7,
    "invoice_number": 0.7,
    "total": 0.7
  },
  "warnings": [],
  "created_at": "2024-03-15T10:30:00+00:00"
}
```

---

## Troubleshooting

### `EnvironmentError: Missing required environment variable(s)`

Make sure `.env` exists at the repo root and all required variables are filled in.
Run `cat .env` (or `Get-Content .env` on PowerShell) to verify.

### `403 PERMISSION_DENIED` from Document AI

- Confirm the service account has the **Document AI API User** role.
- Confirm the API is enabled: `https://console.cloud.google.com/apis/library/documentai.googleapis.com`
- Check `GOOGLE_CLOUD_PROJECT` matches the project where the processor was created.

### `404 NOT_FOUND` – processor not found

- Verify the processor IDs are correct:
  `DOCAI_INVOICE_PROCESSOR_ID`, `DOCAI_RECEIPT_PROCESSOR_ID`, `DOCAI_FORM_PROCESSOR_ID`.
- Verify `DOCAI_LOCATION` matches the region where you created the processor (`us` or `eu`).

### Gemini returns non-JSON / hallucinated values

- The pipeline retries up to 3 times automatically.
- If all retries fail, `extraction.json` will contain `"error": "json_parse_failed"` and the raw response.
- Try a different `--gemini-model` (e.g. `gemini-1.5-flash` for faster responses).

### `google.auth.exceptions.DefaultCredentialsError`

- Ensure `GOOGLE_APPLICATION_CREDENTIALS` points to a valid service-account JSON file.
- On Windows, double-check the path uses forward slashes or double back-slashes.

### `ModuleNotFoundError`

- Make sure you activated the virtual environment before running:

  ```powershell
  .venv\Scripts\Activate.ps1
  ```

- Then re-run `pip install -r requirements.txt`.

### Document AI returns empty text for a scanned PDF

- Check that your processor type supports OCR (Invoice Parser and Document OCR both do).
- Try increasing `--max-pages` or removing the limit entirely.
- Ensure the PDF is not password-protected.

---

## Project structure

```
sme_doc_extract_local/
├── .env.example
├── README.md
├── requirements.txt
├── samples/               ← Place your input PDFs here
├── out/                   ← Generated outputs land here
└── src/
    ├── __init__.py
    ├── main.py            ← CLI entry point
    ├── config.py          ← Env var loading + validation
    ├── constants.py       ← Labels, thresholds, keywords
    ├── schemas.py         ← Pydantic models
    ├── docai_client.py    ← Document AI API calls
    ├── docai_normalize.py ← Text / entity / table extraction
    ├── classify.py        ← Heuristic document classifier
    ├── gemini_client.py   ← Gemini wrapper (retries + JSON cleaning)
    ├── validators.py      ← Validation + normalisation rules
    ├── io_utils.py        ← File I/O and artefact writers
    └── extractors/
        ├── __init__.py
        ├── invoice_extractor.py
        ├── utility_extractor.py
        └── logistics_extractor.py
```
