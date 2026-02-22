"""
gemini_client.py – Wrapper around the Google Generative AI (Gemini) SDK.

Responsibilities
----------------
* Configure the SDK with the API key from Config.
* Accept a text prompt and return cleaned JSON as a Python dict.
* Strip markdown code fences (```json ... ```) that Gemini sometimes emits.
* Retry up to GEMINI_MAX_RETRIES times if JSON parsing fails.
* On total failure return a structured error dict and populate warnings.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import google.generativeai as genai

from src.config import Config
from src.constants import GEMINI_MAX_RETRIES, GEMINI_TEMPERATURE


def configure_gemini(config: Config) -> None:
    """
    Initialise the Gemini SDK with the API key from config.

    Call this once at startup before any ``call_gemini`` invocations.
    """
    genai.configure(api_key=config.gemini_api_key)


def _strip_code_fences(raw: str) -> str:
    """
    Remove markdown code fences so the string can be parsed as JSON.

    Handles:
    * ```json ... ```
    * ``` ... ```
    * bare JSON (no fences)
    """
    # Match an optional ```[lang] at the start and ``` at the end.
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```\s*$"
    match = re.search(pattern, raw.strip(), re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """
    Attempt to parse *text* as JSON.

    Returns the parsed dict or None on failure.
    """
    try:
        data = json.loads(_strip_code_fences(text))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def call_gemini(
    prompt: str,
    config: Config,
    model_name: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Send *prompt* to Gemini and return a parsed JSON dict.

    The function retries up to ``GEMINI_MAX_RETRIES`` times if Gemini's
    response is not valid JSON, with a short back-off between attempts.

    Parameters
    ----------
    prompt:
        The complete prompt string (including any document text snippet).
    config:
        Validated application configuration.
    model_name:
        Override the model specified in config.
    warnings:
        Mutable list – warning strings are appended if issues occur.

    Returns
    -------
    dict
        Parsed extraction dict, or ``{"error": "...", "raw_response": "..."}``
        if all retries fail.
    """
    if warnings is None:
        warnings = []

    chosen_model = model_name or config.gemini_model

    model = genai.GenerativeModel(
        model_name=chosen_model,
        generation_config=genai.types.GenerationConfig(
            temperature=GEMINI_TEMPERATURE,
            response_mime_type="application/json",
        ),
    )

    last_raw: str = ""
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            last_raw = response.text or ""
        except Exception as exc:  # noqa: BLE001
            last_raw = ""
            warnings.append(f"Gemini API error on attempt {attempt}: {exc}")
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(2 ** attempt)
            continue

        parsed = _try_parse_json(last_raw)
        if parsed is not None:
            return parsed

        warnings.append(
            f"Gemini response was not valid JSON on attempt {attempt}. "
            f"Raw (first 300 chars): {last_raw[:300]}"
        )
        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(2 ** attempt)

    # All retries exhausted.
    warnings.append("Gemini failed to return valid JSON after all retries.")
    return {
        "error": "json_parse_failed",
        "raw_response": last_raw[:2000],
    }
