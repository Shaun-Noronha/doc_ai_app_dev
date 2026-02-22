"""
docai_client.py – Thin wrapper around the Google Cloud Document AI API.

Responsibilities
----------------
* Build a DocumentProcessorServiceClient from config.
* Send a PDF (as raw bytes) to a configured processor.
* Return the raw ``google.cloud.documentai.Document`` protobuf object.

The caller is responsible for extracting text / entities from the response
via ``docai_normalize.py``.
"""
from __future__ import annotations

from pathlib import Path

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import documentai

from src.config import Config
from src.constants import PDF_MIME_TYPE, IMAGE_MIME_TYPES


def build_client(config: Config) -> documentai.DocumentProcessorServiceClient:
    """
    Create and return a Document AI client.

    The client uses ADC (Application Default Credentials), which is
    configured via the GOOGLE_APPLICATION_CREDENTIALS env var that
    ``config.py`` sets at startup.

    Parameters
    ----------
    config:
        Validated application configuration.

    Returns
    -------
    DocumentProcessorServiceClient
    """
    client_options = {"api_endpoint": f"{config.docai_location}-documentai.googleapis.com"}
    return documentai.DocumentProcessorServiceClient(client_options=client_options)


def get_mime_type(file_path: Path) -> str:
    """
    Determine MIME type from file extension.
    
    Parameters
    ----------
    file_path:
        Path to the document file.
    
    Returns
    -------
    str
        MIME type string.
    
    Raises
    ------
    ValueError
        If file extension is not supported.
    """
    ext = file_path.suffix.lower()
    
    if ext == ".pdf":
        return PDF_MIME_TYPE
    
    if ext in IMAGE_MIME_TYPES:
        return IMAGE_MIME_TYPES[ext]
    
    raise ValueError(
        f"Unsupported file type: {ext}. "
        f"Allowed: .pdf, {', '.join(IMAGE_MIME_TYPES.keys())}"
    )


def process_pdf(
    pdf_path: Path,
    config: Config,
    client: documentai.DocumentProcessorServiceClient | None = None,
    processor_name: str | None = None,
    max_pages: int | None = None,
) -> documentai.Document:
    """
    Send a local PDF or image file to Document AI and return the parsed Document.

    Parameters
    ----------
    pdf_path:
        Absolute or relative path to the PDF or image file.
    config:
        Validated application configuration.
    client:
        Optional pre-built client (avoids re-connecting on batch runs).
    processor_name:
        Full Document AI processor resource name. If not provided, the
        config's form processor is used.
    max_pages:
        If set, only process the first N pages (PDFs only; ignored for images).

    Returns
    -------
    google.cloud.documentai.Document

    Raises
    ------
    FileNotFoundError
        If ``pdf_path`` does not exist.
    ValueError
        If file extension is not supported.
    GoogleAPICallError
        On any Document AI API failure.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if client is None:
        client = build_client(config)

    # Detect MIME type from extension
    mime_type = get_mime_type(pdf_path)

    raw_document = documentai.RawDocument(
        content=pdf_path.read_bytes(),
        mime_type=mime_type,
    )

    target_processor = processor_name or config.docai_form_processor_name

    # OcrConfig (e.g. enable_native_pdf_parsing) is only supported by Form/Document processors.
    # Invoice Processor and others return 400 if OcrConfig is set.
    use_form_processor = target_processor == config.docai_form_processor_name

    process_options: documentai.ProcessOptions | None = None
    # Only apply page limits for PDFs (images are single-page)
    if mime_type == PDF_MIME_TYPE and max_pages is not None and max_pages > 0:
        process_options = documentai.ProcessOptions(
            individual_page_selector=documentai.ProcessOptions.IndividualPageSelector(
                pages=list(range(1, max_pages + 1))
            )
        )
    elif use_form_processor:
        process_options = documentai.ProcessOptions(
            ocr_config=documentai.OcrConfig(enable_native_pdf_parsing=True)
        )

    request_kwargs: dict = {
        "name": target_processor,
        "raw_document": raw_document,
    }
    if process_options is not None:
        request_kwargs["process_options"] = process_options

    try:
        response: documentai.ProcessResponse = client.process_document(
            request=documentai.ProcessRequest(**request_kwargs)
        )
    except GoogleAPICallError as exc:
        raise GoogleAPICallError(
            f"Document AI call failed for '{pdf_path.name}': {exc}"
        ) from exc
    return response.document
