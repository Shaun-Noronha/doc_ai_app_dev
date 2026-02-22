"""
classify.py – Heuristic document-type classifier.

Uses keyword counting on the extracted plain text.  If the CLI caller
explicitly passes --doc-type, this module is bypassed entirely.
"""
from __future__ import annotations

from src.constants import (
    CLASSIFIER_PATTERNS,
    DOC_TYPE_DELIVERY_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_LOGISTICS,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_UNKNOWN,
    DOC_TYPE_UTILITY,
    DOC_TYPE_UTILITY_BILL,
)


def _count_hits(text_lower: str, keywords: list[str]) -> int:
    """Count how many keywords appear in ``text_lower``."""
    return sum(1 for kw in keywords if kw in text_lower)


def classify_doc(text: str) -> str:
    """
    Classify a document into one of: invoice | receipt | delivery_receipt |
    utility_bill | unknown.

    The classifier converts the text to lower-case and counts keyword hits
    for each document type.  The type with the most hits wins, provided it
    meets the minimum hit threshold; otherwise returns ``unknown``.

    Parameters
    ----------
    text:
        Plain text extracted from the document (e.g. from Document AI).

    Returns
    -------
    str
        One of the ``DOC_TYPE_*`` constants.
    """
    if not text or not text.strip():
        return DOC_TYPE_UNKNOWN

    text_lower = text.lower()

    scores: dict[str, int] = {}
    for doc_type, pattern in CLASSIFIER_PATTERNS.items():
        scores[doc_type] = _count_hits(text_lower, pattern["keywords"])

    if not scores:
        return DOC_TYPE_UNKNOWN

    best_type = max(scores, key=scores.__getitem__)
    if scores[best_type] == 0:
        return DOC_TYPE_UNKNOWN

    return best_type


def classify_doc_with_scores(text: str) -> tuple[str, dict[str, int]]:
    """
    Like ``classify_doc`` but also returns the raw score map for debugging.

    Returns
    -------
    (doc_type, scores_dict)
    """
    if not text or not text.strip():
        return DOC_TYPE_UNKNOWN, {}

    text_lower = text.lower()
    scores: dict[str, int] = {}
    for doc_type, pattern in CLASSIFIER_PATTERNS.items():
        scores[doc_type] = _count_hits(text_lower, pattern["keywords"])

    if not scores:
        return DOC_TYPE_UNKNOWN, {}

    best_type = max(scores, key=scores.__getitem__)
    result = best_type if scores[best_type] > 0 else DOC_TYPE_UNKNOWN
    return result, scores
