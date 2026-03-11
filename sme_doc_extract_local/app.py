"""
app.py – Stub. The web API is now served by the FastAPI backend only.

Run the single backend from the repo root:
    uvicorn dashboard_api.main:app --reload --port 8000

Upload and confirm run in-process via sme_doc_extract_local.service.
For CLI (process, batch, ingest), use: python -m src.main ...
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    print(
        "The Flask app has been removed. Use the FastAPI backend instead:\n"
        "  uvicorn dashboard_api.main:app --reload --port 8000\n"
        "From the doc_ai_app_dev repo root.",
        file=sys.stderr,
    )
    sys.exit(1)
