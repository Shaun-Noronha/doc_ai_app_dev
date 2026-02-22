"""
main.py – CLI entry point for the SME document extraction pipeline.

Usage
-----
Process one file:
    python -m src.main process --file "samples/invoice1.pdf"
    python -m src.main process --file "samples/receipt.jpg"

Process a directory:
    python -m src.main batch --dir "samples/"

Common options:
    --outdir "out/"
    --max-pages N (PDFs only)
    --gemini-model "gemini-2.5-flash"
    --verbose

Note: docai.json is saved by default for debugging (always included).
Document type is always determined automatically via keyword classification
on the initial OCR output — no manual override is supported.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.classify import classify_doc_with_scores
from src.config import get_config
import src.config  # noqa: F401 – load .env for ingest
from src.db import (
    apply_schema,
    fetch_documents,
    fetch_table_counts,
    get_connection,
    insert_category,
    insert_document,
    test_connection,
)
from src.constants import (
    DOC_TYPE_DELIVERY_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_UNKNOWN,
    DOC_TYPE_UTILITY,
    DOC_TYPE_UTILITY_BILL,
    DOC_TYPE_LOGISTICS,
    DEFAULT_GEMINI_MODEL,
)
from src.docai_client import build_client, process_pdf
from src.docai_normalize import build_enriched_text, normalize
from src.extractors.invoice_extractor import extract_invoice
from src.extractors.logistics_extractor import extract_logistics
from src.extractors.utility_extractor import extract_utility
from src.gemini_client import configure_gemini
from src.io_utils import (
    build_extraction_payload,
    build_meta,
    collect_files,
    write_all_artifacts,
)
from src.validators import validate

console = Console()


# ─────────────────────────────────────────────────────────────
# Core pipeline helpers
# ─────────────────────────────────────────────────────────────

def _docai_to_serialisable(document: Any) -> dict:
    """
    Convert a Document AI Document proto to a JSON-serialisable dict.

    Uses the built-in ``to_json()`` helper from the protobuf/gapic wrapper.
    Falls back to an empty dict on failure.
    """
    try:
        import json
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(document._pb)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        try:
            import json
            return json.loads(type(document).to_json(document))
        except Exception:  # noqa: BLE001
            return {}


_EXTRACTOR_MAP = {
    DOC_TYPE_INVOICE:  extract_invoice,
    DOC_TYPE_UTILITY:  extract_utility,
    DOC_TYPE_LOGISTICS: extract_logistics,
}

# Maps each classified doc type to the most accurate Document AI processor.
# invoice  → Invoice Parser  (structured entity extraction)
# receipt  → Receipt Parser  (structured entity extraction)
# delivery_receipt / utility_bill → Form Parser (generic OCR)
# unknown  → Form Parser (fallback)
_PROCESSOR_MAP: dict[str, Any] = {
    DOC_TYPE_INVOICE:          lambda cfg: cfg.docai_invoice_processor_name,
    DOC_TYPE_RECEIPT:          lambda cfg: cfg.docai_receipt_processor_name,
    DOC_TYPE_DELIVERY_RECEIPT: lambda cfg: cfg.docai_form_processor_name,
    DOC_TYPE_UTILITY_BILL:     lambda cfg: cfg.docai_form_processor_name,
}


def _processor_for_doc_type(doc_type: str, config: Any) -> str:
    """Return the Document AI processor resource name for *doc_type*."""
    getter = _PROCESSOR_MAP.get(doc_type)
    if getter is not None:
        return getter(config)
    return config.docai_form_processor_name


def _doc_type_for_extraction(doc_type: str) -> str:
    """Map classifier doc types to supported extraction schemas."""
    if doc_type == DOC_TYPE_RECEIPT:
        return DOC_TYPE_INVOICE
    if doc_type == DOC_TYPE_DELIVERY_RECEIPT:
        return DOC_TYPE_LOGISTICS
    if doc_type == DOC_TYPE_UTILITY_BILL:
        return DOC_TYPE_UTILITY
    return doc_type


def _call_docai(
    pdf_path: Path,
    processor_name: str,
    config: Any,
    client: Any,
    max_pages: int | None,
) -> Any | None:
    """
    Call Document AI and return the Document object.

    Returns ``None`` on failure and prints an error to the console.
    """
    try:
        return process_pdf(
            pdf_path=pdf_path,
            config=config,
            client=client,
            processor_name=processor_name,
            max_pages=max_pages,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]✗[/] Document AI failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────

def process_single(
    pdf_path: Path,
    *,
    outdir: Path,
    max_pages: int | None = None,
    config: Any,
    docai_client: Any,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run the full extraction pipeline on a single PDF or image.

    Steps
    -----
    1a. Pass 1 OCR with the Form Processor (generic OCR for all file types).
    1b. Classify the document via keyword matching.
    1c. Select the most accurate processor for the classified type.
    1d. Pass 2 — re-parse with the specific processor if it differs from the
        Form Processor (invoice → Invoice Parser, receipt → Receipt Parser).
    2.  Normalise Document AI output and build enriched text.
    3.  Gemini extraction using the type-specific prompt.
    4.  Validate and normalise Gemini output.
    5.  Write all artefacts to disk.

    Returns a summary dict with ``status``, ``doc_type``, ``output_dir``.
    """
    warnings: list[str] = []
    t_start = time.monotonic()

    pdf_path = Path(pdf_path).resolve()
    source_file_str = str(pdf_path)
    form_processor = config.docai_form_processor_name

    # ── Step 1a: Pass 1 – Form Processor OCR ──────────────────
    if verbose:
        console.print(f"  [cyan]→[/] Pass 1 OCR on [bold]{pdf_path.name}[/] …")

    document = _call_docai(pdf_path, form_processor, config, docai_client, max_pages)

    if document is None:
        elapsed = time.monotonic() - t_start
        err_msg = "Document AI (Pass 1) failed. See console output above."
        meta = build_meta(
            source_file=source_file_str,
            status="failed",
            processor_name=form_processor,
            gemini_model=config.gemini_model,
            page_count=0,
            elapsed_seconds=elapsed,
            doc_type=DOC_TYPE_UNKNOWN,
            error=err_msg,
        )
        write_all_artifacts(
            pdf_path=pdf_path,
            outdir=outdir,
            raw_text="",
            extraction_payload={
                "source_file": source_file_str,
                "doc_type": DOC_TYPE_UNKNOWN,
                "extraction_method": "document_ai + gemini",
                "extraction": {},
                "confidence": {},
                "warnings": [err_msg],
                "created_at": meta["created_at"],
            },
            warnings=[err_msg],
            meta=meta,
        )
        return {"status": "failed", "doc_type": DOC_TYPE_UNKNOWN, "output_dir": str(outdir / pdf_path.stem)}

    # ── Step 1b: Classify via keyword matching ─────────────────
    norm = normalize(document)
    doc_type, scores = classify_doc_with_scores(norm.full_text)

    if verbose:
        console.print(f"  [cyan]→[/] Classified as [bold]{doc_type}[/] (scores={scores})")

    if doc_type == DOC_TYPE_UNKNOWN:
        warnings.append(
            "Document type could not be confidently classified. "
            "Extraction may be incomplete."
        )

    # ── Step 1c: Select specific processor ────────────────────
    target_processor = _processor_for_doc_type(doc_type, config)

    # ── Step 1d: Pass 2 – re-parse if a better processor exists
    if target_processor != form_processor:
        if verbose:
            console.print(f"  [cyan]→[/] Pass 2 re-parse with [bold]{target_processor}[/] …")

        reparse_doc = _call_docai(pdf_path, target_processor, config, docai_client, max_pages)
        if reparse_doc is not None:
            document = reparse_doc
        else:
            warnings.append(
                f"Pass 2 re-parse failed with processor '{target_processor}'. "
                "Using Pass 1 OCR output."
            )

    # ── Step 2: Normalise Document AI output ──────────────────
    norm = normalize(document)
    enriched_text = build_enriched_text(norm)
    page_count = norm.page_count

    if verbose:
        console.print(
            f"  [green]✓[/] Document AI done. "
            f"Pages={page_count}, text_chars={len(norm.full_text):,}"
        )

    extraction_doc_type = _doc_type_for_extraction(doc_type)
    if extraction_doc_type != doc_type:
        warnings.append(
            f"Using '{extraction_doc_type}' extraction schema for doc_type '{doc_type}'."
        )

    # ── Step 3: Gemini extraction ──────────────────────────────
    extractor = _EXTRACTOR_MAP.get(extraction_doc_type)
    raw_extraction: dict[str, Any] = {}

    if extractor is None:
        warnings.append(
            f"No extractor for doc_type='{doc_type}'. Skipping Gemini extraction."
        )
    else:
        if verbose:
            console.print(f"  [cyan]→[/] Running Gemini ({config.gemini_model}) …")
        raw_extraction = extractor(enriched_text, config=config, warnings=warnings)

    # ── Step 4: Validate ───────────────────────────────────────
    normalised, val_warnings, confidence = validate(extraction_doc_type, raw_extraction)
    warnings.extend(val_warnings)

    elapsed = time.monotonic() - t_start

    # ── Step 5: Write artefacts ────────────────────────────────
    extraction_payload = build_extraction_payload(
        source_file=source_file_str,
        doc_type=doc_type,
        extraction=normalised,
        confidence=confidence,
        warnings=warnings,
    )

    meta = build_meta(
        source_file=source_file_str,
        status="success",
        processor_name=target_processor,
        gemini_model=config.gemini_model,
        page_count=page_count,
        elapsed_seconds=elapsed,
        doc_type=doc_type,
        confidence_summary=confidence,
    )

    docai_raw = _docai_to_serialisable(document)

    paths = write_all_artifacts(
        pdf_path=pdf_path,
        outdir=outdir,
        raw_text=enriched_text,
        extraction_payload=extraction_payload,
        warnings=warnings,
        meta=meta,
        docai_raw=docai_raw,
        save_docai_json=True,
    )

    if verbose:
        console.print(
            f"  [green]✓[/] Artefacts written to [bold]{outdir / pdf_path.stem}[/] "
            f"({len(paths)} files, {elapsed:.1f}s)"
        )

    return {
        "status": "success",
        "doc_type": doc_type,
        "output_dir": str(outdir / pdf_path.stem),
        "warnings": len(warnings),
        "elapsed_seconds": elapsed,
    }


# ─────────────────────────────────────────────────────────────
# CLI commands
# ─────────────────────────────────────────────────────────────

def cmd_process(args: argparse.Namespace) -> int:
    """Handle: python -m src.main process --file ..."""
    pdf_path = Path(args.file)
    if not pdf_path.exists():
        console.print(f"[red]Error:[/] File not found: {pdf_path}")
        return 1

    try:
        config = get_config(gemini_model=args.gemini_model)
    except EnvironmentError as exc:
        console.print(f"[red]Config error:[/] {exc}")
        return 1

    configure_gemini(config)
    docai_client = build_client(config)
    outdir = Path(args.outdir)

    console.print(Panel(f"[bold]Processing[/]: {pdf_path.name}", style="blue"))

    result = process_single(
        pdf_path=pdf_path,
        outdir=outdir,
        max_pages=args.max_pages,
        config=config,
        docai_client=docai_client,
        verbose=args.verbose,
    )

    _print_result_table([result])
    return 0 if result["status"] == "success" else 1


def cmd_batch(args: argparse.Namespace) -> int:
    """Handle: python -m src.main batch --dir ..."""
    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        console.print(f"[red]Error:[/] Directory not found: {src_dir}")
        return 1

    files = collect_files(src_dir)
    if not files:
        console.print(f"[yellow]Warning:[/] No PDF or image files found in {src_dir}")
        return 0

    try:
        config = get_config(gemini_model=args.gemini_model)
    except EnvironmentError as exc:
        console.print(f"[red]Config error:[/] {exc}")
        return 1

    configure_gemini(config)
    docai_client = build_client(config)
    outdir = Path(args.outdir)

    console.print(
        Panel(
            f"[bold]Batch processing[/]: {len(files)} file(s) in [italic]{src_dir}[/]",
            style="blue",
        )
    )

    results: list[dict] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing …", total=len(files))
        for pdf_path in files:
            progress.update(task, description=f"[cyan]{pdf_path.name}[/]")
            try:
                result = process_single(
                    pdf_path=pdf_path,
                    outdir=outdir,
                    max_pages=args.max_pages,
                    config=config,
                    docai_client=docai_client,
                    verbose=args.verbose,
                )
            except Exception as exc:  # noqa: BLE001
                console.print(f"  [red]✗[/] Unexpected error on {pdf_path.name}: {exc}")
                if args.verbose:
                    console.print(traceback.format_exc())
                result = {
                    "status": "failed",
                    "doc_type": DOC_TYPE_UNKNOWN,
                    "output_dir": str(outdir / pdf_path.stem),
                    "warnings": 1,
                    "elapsed_seconds": 0.0,
                    "file": pdf_path.name,
                }
            result.setdefault("file", pdf_path.name)
            results.append(result)
            progress.advance(task)

    _print_result_table(results)
    failed = sum(1 for r in results if r["status"] != "success")
    return 0 if failed == 0 else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Handle: python -m src.main ingest --outdir out. Load extraction.json files into the database."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        console.print(
            "[red]Error:[/] DATABASE_URL is not set. Set it in .env or the environment."
        )
        return 1

    outdir = Path(args.outdir)
    if not outdir.exists():
        console.print(f"[red]Error:[/] Outdir not found: {outdir}")
        return 1

    files = sorted(outdir.rglob("extraction.json"))
    if not files:
        console.print(f"[yellow]Warning:[/] No extraction.json files found under {outdir}")
        return 0

    console.print(
        Panel(
            f"[bold]Ingesting[/]: {len(files)} extraction.json file(s) from [italic]{outdir}[/]",
            style="blue",
        )
    )

    inserted = 0
    with_category = 0
    failed = 0
    conn = get_connection(database_url)
    try:
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                doc_id = insert_document(conn, payload)
                had_category = insert_category(conn, doc_id, payload)
                conn.commit()
                inserted += 1
                if had_category:
                    with_category += 1
                if args.verbose:
                    detail = "document + parsed_*" if had_category else "document only"
                    console.print(
                        f"  [green]✓[/] {path.relative_to(outdir)} → document_id {doc_id} ({detail})"
                    )
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                failed += 1
                console.print(f"  [red]✗[/] {path}: {exc}")
                if args.verbose:
                    console.print(traceback.format_exc())
    finally:
        conn.close()

    console.print(
        f"[bold]Done.[/] Inserted: [green]{inserted}[/] documents "
        f"([cyan]{with_category}[/] with parsed_* row), failed: [red]{failed}[/]"
    )
    if inserted > 0 and with_category < inserted - failed:
        console.print(
            "[dim]Note: Only utility_bill (electricity/gas/water) and delivery_receipt/shipping "
            "get a parsed_* row. Invoices/receipts and failed extractions are stored in documents only.[/]"
        )
    return 0 if failed == 0 else 1


def cmd_test_db(_args: argparse.Namespace) -> int:
    """Handle: python -m src.main test-db. Verify PostgreSQL connection (DATABASE_URL)."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        console.print(
            "[red]Error:[/] DATABASE_URL is not set. Set it in .env or the environment."
        )
        return 1
    ok, err = test_connection(database_url)
    if ok:
        console.print("[green]PostgreSQL connection OK.[/]")
        return 0
    console.print(f"[red]PostgreSQL connection failed:[/] {err}")
    return 1


def cmd_fetch_db(args: argparse.Namespace) -> int:
    """Handle: python -m src.main fetch-db. Query and print data from the database."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        console.print(
            "[red]Error:[/] DATABASE_URL is not set. Set it in .env or the environment."
        )
        return 1

    # Table counts
    counts = fetch_table_counts(database_url)
    table = Table(title="Table row counts")
    table.add_column("Table", style="cyan")
    table.add_column("Count", justify="right", style="green")
    for name, count in counts.items():
        table.add_row(name, str(count) if count >= 0 else "(error)")
    console.print(table)
    console.print()

    # Recent documents
    limit = getattr(args, "limit", 50)
    doc_type_filter = getattr(args, "document_type", None)
    rows = fetch_documents(database_url, limit=limit, document_type=doc_type_filter)
    doc_table = Table(title=f"Documents (most recent, limit={limit})")
    doc_table.add_column("document_id", justify="right", style="dim")
    doc_table.add_column("document_type", style="cyan")
    doc_table.add_column("source_filename", style="white")
    doc_table.add_column("created_at", style="dim")
    for r in rows:
        doc_table.add_row(
            str(r["document_id"]),
            r["document_type"] or "",
            (r["source_filename"] or "")[:60],
            str(r["created_at"]) if r.get("created_at") else "",
        )
    console.print(doc_table)
    return 0


def cmd_init_db(_args: argparse.Namespace) -> int:
    """Handle: python -m src.main init-db. Apply schema (documents + category tables) to PostgreSQL."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        console.print(
            "[red]Error:[/] DATABASE_URL is not set. Set it in .env or the environment."
        )
        return 1
    console.print("[cyan]Applying schema (schema/documents.sql) …[/]")
    ok, err = apply_schema(database_url)
    if ok:
        console.print("[green]Schema applied successfully.[/]")
        return 0
    console.print(f"[red]Schema apply failed:[/] {err}")
    return 1


def _print_result_table(results: list[dict]) -> None:
    """Render a rich summary table of processing results."""
    table = Table(title="Extraction Results", show_lines=True)
    table.add_column("File", style="bold")
    table.add_column("Status")
    table.add_column("Doc Type")
    table.add_column("Warnings", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Output Dir")

    for r in results:
        status_str = "[green]success[/]" if r.get("status") == "success" else "[red]failed[/]"
        table.add_row(
            r.get("file", ""),
            status_str,
            r.get("doc_type", ""),
            str(r.get("warnings", "")),
            f"{r.get('elapsed_seconds', 0):.1f}",
            r.get("output_dir", ""),
        )
    console.print(table)


# ─────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────

def _build_shared_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by both sub-commands."""
    parser.add_argument(
        "--outdir",
        default="out",
        help="Root output directory (default: out/)",
    )
    parser.add_argument(
        "--save-docai-json",
        action="store_true",
        default=True,
        dest="save_docai_json",
        help="Save raw Document AI response as docai.json (default: on)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        dest="max_pages",
        help="Maximum number of pages to process (default: all)",
    )
    parser.add_argument(
        "--gemini-model",
        default=DEFAULT_GEMINI_MODEL,
        dest="gemini_model",
        help=f"Gemini model name (default: {DEFAULT_GEMINI_MODEL})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print detailed progress to console",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argument parser."""
    root = argparse.ArgumentParser(
        prog="python -m src.main",
        description="SME Document Extraction Pipeline – local CLI tool.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    # ── process (single file) ──────────────────────────────────
    p_process = sub.add_parser("process", help="Process a single PDF file.")
    p_process.add_argument(
        "--file",
        required=True,
        help='Path to PDF or image file, e.g. "samples/invoice1.pdf" or "receipt.jpg"',
    )
    _build_shared_args(p_process)

    # ── batch (directory) ──────────────────────────────────────
    p_batch = sub.add_parser("batch", help="Process all PDFs in a directory.")
    p_batch.add_argument(
        "--dir",
        required=True,
        help='Directory containing PDF/image files, e.g. "samples/"',
    )
    _build_shared_args(p_batch)

    # ── ingest (load extraction.json into database) ──────────────
    p_ingest = sub.add_parser(
        "ingest",
        help="Load extraction.json files from an outdir into the database (requires DATABASE_URL).",
    )
    p_ingest.add_argument(
        "--outdir",
        default="out",
        help="Root output directory containing extraction.json files (default: out)",
    )
    p_ingest.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print each file as it is ingested",
    )

    # ── test-db (verify PostgreSQL connection) ───────────────────
    sub.add_parser(
        "test-db",
        help="Test PostgreSQL connection using DATABASE_URL.",
    )

    # ── init-db (apply schema to PostgreSQL) ──────────────────────
    sub.add_parser(
        "init-db",
        help="Apply schema (documents + category tables) to the database. Requires DATABASE_URL.",
    )

    # ── fetch-db (query and print data from PostgreSQL) ───────────
    p_fetch = sub.add_parser(
        "fetch-db",
        help="Fetch and print documents and table counts from the database (requires DATABASE_URL).",
    )
    p_fetch.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of documents to list (default 50)",
    )
    p_fetch.add_argument(
        "--document-type",
        dest="document_type",
        default=None,
        help="Filter documents by document_type (e.g. utility_bill, invoice)",
    )

    return root


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    """Parse arguments and dispatch to the correct sub-command."""
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "process": cmd_process,
        "batch": cmd_batch,
        "ingest": cmd_ingest,
        "test-db": cmd_test_db,
        "init-db": cmd_init_db,
        "fetch-db": cmd_fetch_db,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
