"""
io_utils.py – File I/O helpers and output artefact writers.

All output is written to a sub-directory of *outdir* named after the PDF stem:
    outdir/<stem>/
        raw_text.txt
        extraction.json
        warnings.json          (standalone, optional)
        docai.json             (optional, only when --save-docai-json)
        meta.json

None of these functions raise on missing parent directories – they are created
automatically via ``Path.mkdir(parents=True)``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.constants import (
    ALLOWED_EXTENSIONS,
    OUT_DOCAI,
    OUT_EXTRACTION,
    OUT_META,
    OUT_RAW_TEXT,
    OUT_WARNINGS,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Serialise *data* to JSON at *path*, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False, default=str)


def _write_text(path: Path, text: str) -> None:
    """Write *text* to *path*, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stem_outdir(pdf_path: Path, outdir: Path) -> Path:
    """
    Return the output sub-directory for a given PDF or image.

    Example: pdf=``samples/invoice1.pdf``, outdir=``out/`` →  ``out/invoice1/``
    """
    return outdir / pdf_path.stem


def collect_files(input_dir: Path) -> list[Path]:
    """
    Collect all PDF and image files from a directory (non-recursive).

    Parameters
    ----------
    input_dir:
        Directory to scan.

    Returns
    -------
    list[Path]
        Sorted list of file paths with allowed extensions.
    """
    files = [
        f
        for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    return sorted(files)


# ─────────────────────────────────────────────────────────────
# Individual artefact writers
# ─────────────────────────────────────────────────────────────

def write_raw_text(pdf_path: Path, outdir: Path, text: str) -> Path:
    """Write the OCR plain text and return the output path."""
    dest = stem_outdir(pdf_path, outdir) / OUT_RAW_TEXT
    _write_text(dest, text)
    return dest


def write_extraction(pdf_path: Path, outdir: Path, payload: dict[str, Any]) -> Path:
    """Write the final extraction JSON and return the output path."""
    dest = stem_outdir(pdf_path, outdir) / OUT_EXTRACTION
    _write_json(dest, payload)
    return dest


def write_warnings(pdf_path: Path, outdir: Path, warnings: list[str]) -> Path:
    """Write warnings as a standalone JSON array and return the output path."""
    dest = stem_outdir(pdf_path, outdir) / OUT_WARNINGS
    _write_json(dest, warnings)
    return dest


def write_docai_json(pdf_path: Path, outdir: Path, docai_data: dict[str, Any]) -> Path:
    """Write the raw Document AI response JSON and return the output path."""
    dest = stem_outdir(pdf_path, outdir) / OUT_DOCAI
    _write_json(dest, docai_data)
    return dest


def write_meta(pdf_path: Path, outdir: Path, meta: dict[str, Any]) -> Path:
    """Write meta.json (timing, model info, page count, status) and return path."""
    dest = stem_outdir(pdf_path, outdir) / OUT_META
    _write_json(dest, meta)
    return dest


# ─────────────────────────────────────────────────────────────
# Composite writer
# ─────────────────────────────────────────────────────────────

def write_all_artifacts(
    *,
    pdf_path: Path,
    outdir: Path,
    raw_text: str,
    extraction_payload: dict[str, Any],
    warnings: list[str],
    meta: dict[str, Any],
    docai_raw: dict[str, Any] | None = None,
    save_docai_json: bool = False,
) -> dict[str, Path]:
    """
    Write all output artefacts for a single processed PDF.

    Parameters
    ----------
    pdf_path:       Source PDF file (used to derive the sub-directory name).
    outdir:         Root output directory.
    raw_text:       Plain text from Document AI.
    extraction_payload: The complete extraction.json dict.
    warnings:       List of warning strings.
    meta:           Meta information dict.
    docai_raw:      Raw Document AI response (serialisable dict).
    save_docai_json: Whether to persist ``docai.json``.

    Returns
    -------
    Mapping of artefact key → written file path.
    """
    paths: dict[str, Path] = {}

    paths["raw_text"] = write_raw_text(pdf_path, outdir, raw_text)
    paths["extraction"] = write_extraction(pdf_path, outdir, extraction_payload)
    paths["warnings"] = write_warnings(pdf_path, outdir, warnings)
    paths["meta"] = write_meta(pdf_path, outdir, meta)

    if save_docai_json and docai_raw is not None:
        paths["docai"] = write_docai_json(pdf_path, outdir, docai_raw)

    return paths


# ─────────────────────────────────────────────────────────────
# Utility: build the extraction.json payload
# ─────────────────────────────────────────────────────────────

def build_extraction_payload(
    *,
    source_file: str,
    doc_type: str,
    extraction: dict[str, Any],
    confidence: dict[str, float],
    warnings: list[str],
) -> dict[str, Any]:
    """
    Assemble the canonical extraction.json dict.

    Parameters
    ----------
    source_file:   Relative path string for the source PDF.
    doc_type:      Classified or forced document type.
    extraction:    Validated extraction fields.
    confidence:    Field-level confidence scores.
    warnings:      Accumulated warning strings.

    Returns
    -------
    dict ready to be serialised as extraction.json.
    """
    return {
        "source_file": source_file,
        "doc_type": doc_type,
        "extraction_method": "document_ai + gemini",
        "extraction": extraction,
        "confidence": confidence,
        "warnings": warnings,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def build_meta(
    *,
    source_file: str,
    status: str,
    processor_name: str,
    gemini_model: str,
    page_count: int,
    elapsed_seconds: float,
    doc_type: str,
    confidence_summary: dict[str, float] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Build the meta.json dict.

    Parameters
    ----------
    source_file:        Relative path to the source PDF.
    status:             "success" | "failed" | "partial".
    processor_name:     Full Document AI processor resource name.
    gemini_model:       Gemini model name used.
    page_count:         Number of pages processed by Document AI.
    elapsed_seconds:    Wall-clock seconds for the whole pipeline.
    doc_type:           Detected / forced document type.
    confidence_summary: Average or per-field confidence dict.
    error:              Error message if status == "failed".

    Returns
    -------
    dict ready to be serialised as meta.json.
    """
    meta: dict[str, Any] = {
        "source_file": source_file,
        "status": status,
        "doc_type": doc_type,
        "processor": processor_name,
        "gemini_model": gemini_model,
        "page_count": page_count,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if confidence_summary:
        meta["confidence_summary"] = confidence_summary
    if error:
        meta["error"] = error
    return meta
