"""
invoice_extractor.py – Extract structured invoice fields via Gemini.

Prompt design
-------------
The prompt instructs Gemini to return ONLY a JSON object matching the
InvoiceSchema.  It explicitly forbids inventing values and requires ISO
dates and numeric-only numbers.
"""
from __future__ import annotations

from typing import Any

from src.config import Config
from src.gemini_client import call_gemini

# ── Prompt template ───────────────────────────────────────────────────────────
_INVOICE_PROMPT_TEMPLATE = """\
You are a precise document data-extraction assistant.

Your task: extract structured invoice information from the document text below
and return it as a single JSON object — nothing else, no explanation, no prose.

RULES:
1. Return ONLY valid JSON. No markdown fences, no prose, no comments.
2. Use null (JSON null) for any field that is absent or unreadable.
3. Dates MUST be ISO format: YYYY-MM-DD.
4. Numeric fields MUST be plain numbers (strip currency symbols and commas).
5. currency MUST be an ISO 4217 code (e.g. "USD", "EUR", "GBP").
6. Do NOT invent or guess values.

REQUIRED JSON STRUCTURE:
{{
  "vendor_name": string | null,
  "invoice_number": string | null,
  "invoice_date": "YYYY-MM-DD" | null,
  "due_date": "YYYY-MM-DD" | null,
  "currency": "USD" | null,
  "subtotal": number | null,
  "tax": number | null,
  "total": number | null,
  "line_items": [
    {{
      "description": string | null,
      "quantity": number | null,
      "weight": number | null,
      "unit_price": number | null,
      "total_price": number | null,
    }}
  ]
}}

DOCUMENT TEXT:
---
{document_text}
---

Return ONLY the JSON object now.
"""


def extract_invoice(
    document_text: str,
    config: Config,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract invoice fields from *document_text* using Gemini.

    Parameters
    ----------
    document_text:
        Plain text (+ optional table snippets) from Document AI.
    config:
        Validated application config.
    warnings:
        Mutable list – warnings are appended in-place.

    Returns
    -------
    dict matching InvoiceSchema (or error dict on total failure).
    """
    if warnings is None:
        warnings = []

    # Truncate to avoid hitting token limits; keep first 12,000 chars.
    truncated_text = document_text[:12_000]
    prompt = _INVOICE_PROMPT_TEMPLATE.format(document_text=truncated_text)

    return call_gemini(prompt=prompt, config=config, warnings=warnings)
