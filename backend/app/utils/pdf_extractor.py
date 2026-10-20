"""PDF text extraction utility using PyMuPDF."""
from __future__ import annotations
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Import pymupdf (PyMuPDF 2.x) — falls back gracefully
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf  # type: ignore[no-redef]
    except ImportError:
        pymupdf = None  # type: ignore[assignment]

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf"}


def validate_pdf_path(file_path: str) -> None:
    """Validate file path before extraction."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Only PDF files are supported, got: {path.suffix}")
    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large: {size} bytes (max {MAX_FILE_SIZE_BYTES})")
    if size == 0:
        raise ValueError("File is empty")


def extract_text_from_path(file_path: str) -> str:
    """
    Extract text from a PDF file using PyMuPDF (fitz).
    Returns extracted text string.
    Raises ValueError for malformed or unreadable PDFs.
    """
    validate_pdf_path(file_path)

    try:
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is not installed. Run: pip install PyMuPDF")
        doc = pymupdf.open(file_path)
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")

        texts = []
        for page_num in range(min(doc.page_count, 20)):  # Cap at 20 pages
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                texts.append(text)

        doc.close()
        full_text = "\n".join(texts).strip()

        if not full_text:
            raise ValueError("No extractable text found in PDF (may be image-based)")

        logger.info(f"Extracted {len(full_text)} chars from {file_path}")
        return full_text

    except ImportError:
        raise RuntimeError("PyMuPDF is not installed. Run: pip install PyMuPDF")
    except Exception as e:
        if isinstance(e, (ValueError, RuntimeError)):
            raise
        raise ValueError(f"PDF extraction failed: {str(e)}")


def extract_text_safe(file_path: str) -> tuple[Optional[str], Optional[str]]:
    """
    Safe wrapper — returns (text, error_message).
    Never raises exceptions.
    """
    try:
        text = extract_text_from_path(file_path)
        return text, None
    except Exception as e:
        logger.warning(f"PDF extraction failed for {file_path}: {e}")
        return None, str(e)
