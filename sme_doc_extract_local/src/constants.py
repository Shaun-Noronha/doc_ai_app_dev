"""
constants.py – Shared labels, keyword sets, and thresholds.
"""

# ── Document type labels ──────────────────────────────────────
DOC_TYPE_INVOICE = "invoice"
DOC_TYPE_RECEIPT = "receipt"
DOC_TYPE_DELIVERY_RECEIPT = "delivery_receipt"
DOC_TYPE_UTILITY_BILL = "utility_bill"
DOC_TYPE_UTILITY = "utility"
DOC_TYPE_LOGISTICS = "logistics"
DOC_TYPE_UNKNOWN = "unknown"

ALLOWED_DOC_TYPES = [
    DOC_TYPE_INVOICE,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_DELIVERY_RECEIPT,
    DOC_TYPE_UTILITY_BILL,
    DOC_TYPE_UTILITY,
    DOC_TYPE_LOGISTICS,
    DOC_TYPE_UNKNOWN,
]
AUTO_CLASSIFY = "auto"

# ── Heuristic keyword sets for classification ─────────────────
CLASSIFIER_PATTERNS = {
    "invoice": {
        "keywords": [
            "commercial invoice",
            "invoice no",
            "invoice number",
            "bill to",
            "ship to",
            "shipworks",
            "po number",
        ],
    },
    "receipt": {
        "keywords": [
            "receipt",
            "thank you",
            "transaction",
            "total paid",
            "card ending",
            "amount tendered",
        ],
    },
    "delivery_receipt": {
        "keywords": [
            "tracking number",
            "delivered by",
            "proof of delivery",
            "carrier",
            "shipment",
            "packages",
            "signed by",
        ],
    },
    "utility_bill": {
        "keywords": [
            "account number",
            "meter reading",
            "kwh",
            "usage",
            "service period",
            "billing period",
            "previous balance",
        ],
    },
}

# ── Gemini defaults ───────────────────────────────────────────
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MAX_RETRIES = 3
GEMINI_TEMPERATURE = 0.0

# ── Validation tolerances ─────────────────────────────────────
# Allowed absolute difference: subtotal + tax vs total
INVOICE_TOTAL_TOLERANCE = 1.0

# ── Confidence scores ─────────────────────────────────────────
CONFIDENCE_PRESENT_VALID = 0.7
CONFIDENCE_PRESENT_INVALID = 0.4
CONFIDENCE_MISSING = 0.0

# ── Allowed logistics modes ───────────────────────────────────
LOGISTICS_ALLOWED_MODES = {"truck", "air", "sea", "rail"}

# ── Output file names ─────────────────────────────────────────
OUT_RAW_TEXT = "raw_text.txt"
OUT_EXTRACTION = "extraction.json"
OUT_WARNINGS = "warnings.json"
OUT_DOCAI = "docai.json"
OUT_META = "meta.json"

# ── MIME type ─────────────────────────────────────────────────
PDF_MIME_TYPE = "application/pdf"
IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# Combined allowed extensions
ALLOWED_EXTENSIONS = {".pdf", *IMAGE_MIME_TYPES.keys()}
