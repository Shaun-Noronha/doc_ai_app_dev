"""
logistics_extractor.py – Extract structured logistics/shipping fields via Gemini.

Prompt design
-------------
The prompt instructs Gemini to return ONLY a JSON object matching the
LogisticsSchema.  It explicitly forbids inventing values and requires ISO
dates, a numeric distance/weight, and a constrained transport mode.
"""
from __future__ import annotations

from typing import Any

from src.config import Config
from src.gemini_client import call_gemini

# ── Prompt template ───────────────────────────────────────────────────────────
_LOGISTICS_PROMPT_TEMPLATE = """\
You are a precise document data-extraction assistant.

Your task: extract structured logistics / shipping information from the document
text below and return it as a single JSON object — nothing else, no explanation.

RULES:
1. Return ONLY valid JSON. No markdown fences, no prose, no comments.
2. Use null (JSON null) for any field that is absent or unreadable.
3. Dates MUST be ISO format: YYYY-MM-DD.
4. Numeric fields MUST be plain numbers (strip units and commas).
5. mode MUST be one of: "truck", "air", "sea", "rail", or null.
6. origin and destination MUST use the sub-object format shown below.
7. Do NOT invent or guess values.

REQUIRED JSON STRUCTURE:
{{
  "shipment_id": string | null,
  "date": "YYYY-MM-DD" | null,
  "carrier": string | null,
  "mode": "truck" | "air" | "sea" | "rail" | null,
  "origin": {{
    "city": string | null,
    "state": string | null,
    "country": string | null
  }} | null,
  "destination": {{
    "city": string | null,
    "state": string | null,
    "country": string | null
  }} | null,
  "distance_km": number | null,
  "weight_kg": number | null,
  "packages_count": integer | null
}}

DOCUMENT TEXT:
---
{document_text}
---

Return ONLY the JSON object now.
"""


def extract_logistics(
    document_text: str,
    config: Config,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Extract logistics fields from *document_text* using Gemini.

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
    dict matching LogisticsSchema (or error dict on total failure).
    """
    if warnings is None:
        warnings = []

    truncated_text = document_text[:12_000]
    prompt = _LOGISTICS_PROMPT_TEMPLATE.format(document_text=truncated_text)

    return call_gemini(prompt=prompt, config=config, warnings=warnings)
