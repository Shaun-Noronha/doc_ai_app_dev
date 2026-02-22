"""
utility_extractor.py – Extract structured utility-bill fields via Gemini.

Prompt design
-------------
The prompt instructs Gemini to return ONLY a JSON object matching the
UtilitySchema.  It explicitly forbids inventing values and requires ISO
dates, numeric-only numbers, and ISO 4217 currency codes.
"""
from __future__ import annotations

from typing import Any

from src.config import Config
from src.gemini_client import call_gemini

# ── Prompt template ───────────────────────────────────────────────────────────
_UTILITY_PROMPT_TEMPLATE = """\
You are a precise document data-extraction assistant.

Your task: extract structured utility bill information from the document text
below and return it as a single JSON object — nothing else, no explanation.

RULES:
1. Return ONLY valid JSON. No markdown fences, no prose, no comments.
2. Use null (JSON null) for any field that is absent or unreadable.
3. Dates MUST be ISO format: YYYY-MM-DD.
4. Numeric fields MUST be plain numbers (strip units, commas, currency symbols).
5. currency MUST be an ISO 4217 code (e.g. "USD").
6. Do NOT invent or guess values.

REQUIRED JSON STRUCTURE:
{{
  "provider": string | null,
  "account_id": string | null,
  "location": string | null,
  "utility_type": "gas" | "water" | "electricity" | "other" | null,
  "billing_period_start": "YYYY-MM-DD" | null,
  "billing_period_end": "YYYY-MM-DD" | null,
  "electricity_kwh": number | null,
  "natural_gas_therms": number | null,
  "water_volume": number | null,
  "water_unit": string | null,
  "total_amount": number | null,
  "currency": "USD" | null
}}

- location: service or billing address as "City, State" (e.g. "Austin, TX"). Omit state if not present.
- utility_type: one of "gas", "water", "electricity", or "other" based on what the bill is for.
- For water bills: water_volume = usage amount (plain number); water_unit = unit from the document (e.g. gal, m³, ccf) or null.

DOCUMENT TEXT:
---
{document_text}
---

Return ONLY the JSON object now.
"""


def extract_utility(
    document_text: str,
    config: Config,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract utility-bill fields from *document_text* using Gemini.

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
    dict matching UtilitySchema (or error dict on total failure).
    """
    if warnings is None:
        warnings = []

    truncated_text = document_text[:12_000]
    prompt = _UTILITY_PROMPT_TEMPLATE.format(document_text=truncated_text)

    return call_gemini(prompt=prompt, config=config, warnings=warnings)
