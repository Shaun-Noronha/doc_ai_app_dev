"""
config.py – Load and validate required environment variables.

All configuration is loaded from environment variables (or a .env file
at the project root).  Call `get_config()` once at startup to obtain a
validated Config object.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from the directory that contains *this* file's parent (repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)


@dataclass
class Config:
    """Validated runtime configuration."""

    google_application_credentials: str
    google_cloud_project: str
    docai_location: str
    docai_invoice_processor_id: str
    docai_receipt_processor_id: str
    docai_form_processor_id: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"

    # Derived – full processor resource names
    docai_invoice_processor_name: str = field(init=False)
    docai_receipt_processor_name: str = field(init=False)
    docai_form_processor_name: str = field(init=False)

    def __post_init__(self) -> None:
        self.docai_invoice_processor_name = self._build_processor_name(
            self.docai_invoice_processor_id
        )
        self.docai_receipt_processor_name = self._build_processor_name(
            self.docai_receipt_processor_id
        )
        self.docai_form_processor_name = self._build_processor_name(
            self.docai_form_processor_id
        )

    def _build_processor_name(self, processor_id: str) -> str:
        return (
            f"projects/{self.google_cloud_project}"
            f"/locations/{self.docai_location}"
            f"/processors/{processor_id}"
        )


_REQUIRED_VARS = [
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "DOCAI_LOCATION",
    "DOCAI_INVOICE_PROCESSOR_ID",
    "DOCAI_RECEIPT_PROCESSOR_ID",
    "DOCAI_FORM_PROCESSOR_ID",
    "GEMINI_API_KEY",
]


def get_config(gemini_model: str | None = None) -> Config:
    """
    Read environment variables, validate presence, and return a Config.

    Parameters
    ----------
    gemini_model:
        Override the Gemini model name (e.g. from CLI flag).

    Raises
    ------
    EnvironmentError
        If any required variable is missing.
    """
    missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}\n"
            "Copy .env.example → .env and fill in the values."
        )

    cfg = Config(
        google_application_credentials=os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        google_cloud_project=os.environ["GOOGLE_CLOUD_PROJECT"],
        docai_location=os.environ["DOCAI_LOCATION"],
        docai_invoice_processor_id=os.environ["DOCAI_INVOICE_PROCESSOR_ID"],
        docai_receipt_processor_id=os.environ["DOCAI_RECEIPT_PROCESSOR_ID"],
        docai_form_processor_id=os.environ["DOCAI_FORM_PROCESSOR_ID"],
        gemini_api_key=os.environ["GEMINI_API_KEY"],
    )

    if gemini_model:
        cfg.gemini_model = gemini_model

    # Point the Google auth library at the supplied key file.
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cfg.google_application_credentials

    return cfg
