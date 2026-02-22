"""
docai_normalize.py – Extract usable text and structure from a Document AI response.

Provides helpers to pull:
* Full plain text (document.text)
* Named entities (if the processor supports them)
* Table content as plain text snippets
"""
from __future__ import annotations

from dataclasses import dataclass, field

from google.cloud import documentai


@dataclass
class NormalizedDocAIResult:
    """Holds the parts we care about from a Document AI Document object."""

    full_text: str = ""
    entities: list[dict] = field(default_factory=list)
    table_snippets: list[str] = field(default_factory=list)
    page_count: int = 0


def _get_text_anchor(document: documentai.Document, text_anchor: documentai.Document.TextAnchor) -> str:
    """
    Reconstruct a substring of ``document.text`` from a TextAnchor.

    Document AI stores all text in ``document.text`` and references
    segments via ``TextAnchor.text_segments``.
    """
    if not text_anchor or not text_anchor.text_segments:
        return ""
    parts: list[str] = []
    for segment in text_anchor.text_segments:
        start = int(segment.start_index)
        end = int(segment.end_index)
        parts.append(document.text[start:end])
    return "".join(parts)


def extract_entities(document: documentai.Document) -> list[dict]:
    """
    Return a flat list of entities as plain dicts.

    Each dict has keys: ``type``, ``mention_text``, ``confidence``.
    Works only when the processor emits entities (e.g. Invoice Parser).
    """
    result: list[dict] = []
    for entity in document.entities:
        result.append(
            {
                "type": entity.type_,
                "mention_text": entity.mention_text.strip() if entity.mention_text else "",
                "confidence": round(entity.confidence, 4) if entity.confidence else None,
            }
        )
    return result


def _table_to_text(document: documentai.Document, table: documentai.Document.Page.Table) -> str:
    """Convert a single Document AI table into a tab-separated plain-text block."""
    rows_text: list[str] = []

    def _extract_row(row: documentai.Document.Page.Table.TableRow) -> str:
        cells: list[str] = []
        for cell in row.cells:
            cell_text = _get_text_anchor(document, cell.layout.text_anchor).replace("\n", " ").strip()
            cells.append(cell_text)
        return "\t".join(cells)

    for header_row in table.header_rows:
        rows_text.append(_extract_row(header_row))
    for body_row in table.body_rows:
        rows_text.append(_extract_row(body_row))

    return "\n".join(rows_text)


def extract_tables(document: documentai.Document) -> list[str]:
    """
    Return each detected table as a newline+tab-separated string.

    Not all processors detect tables; returns an empty list if none.
    """
    snippets: list[str] = []
    for page in document.pages:
        for table in page.tables:
            text = _table_to_text(document, table)
            if text.strip():
                snippets.append(text)
    return snippets


def normalize(document: documentai.Document) -> NormalizedDocAIResult:
    """
    Extract all useful components from a Document AI ``Document`` object.

    Parameters
    ----------
    document:
        The raw Document AI response document.

    Returns
    -------
    NormalizedDocAIResult
    """
    entities = extract_entities(document)
    tables = extract_tables(document)
    
    print(f"[DEBUG] Found {len(entities)} entities")
    print(f"[DEBUG] Found {len(tables)} tables")
    if entities:
        print(f"[DEBUG] First entity: {entities[0]}")
    
    return NormalizedDocAIResult(
        full_text=document.text or "",
        entities=entities,
        table_snippets=tables,
        page_count=len(document.pages),
    )


def build_enriched_text(result: NormalizedDocAIResult) -> str:
    """
    Combine full_text with any table snippets into a single rich-text block
    suitable for passing to Gemini.

    Tables are appended at the end under a ``[TABLES]`` header so Gemini
    can use them for line-item extraction.
    """
    parts: list[str] = [result.full_text.strip()]
    if result.table_snippets:
        parts.append("\n\n[TABLES]\n")
        for i, snippet in enumerate(result.table_snippets, start=1):
            parts.append(f"--- Table {i} ---\n{snippet}")
    return "\n".join(parts)
