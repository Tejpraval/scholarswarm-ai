"""Tests for PDF extraction utility."""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.utils.pdf_extractor import (
    extract_text_from_path, extract_text_safe, validate_pdf_path
)


class TestPDFValidation:
    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_pdf_path("/nonexistent/path/file.pdf")

    def test_wrong_extension_raises(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="Only PDF files"):
            validate_pdf_path(str(txt_file))

    def test_empty_file_raises(self, tmp_path):
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            validate_pdf_path(str(pdf_file))

    def test_file_too_large_raises(self, tmp_path):
        pdf_file = tmp_path / "big.pdf"
        pdf_file.write_bytes(b"x" * (11 * 1024 * 1024))  # 11MB
        with pytest.raises(ValueError, match="too large"):
            validate_pdf_path(str(pdf_file))


class TestExtractTextSafe:
    def test_returns_none_on_error(self):
        text, error = extract_text_safe("/nonexistent/file.pdf")
        assert text is None
        assert error is not None

    def test_returns_text_on_success(self, tmp_path):
        """Test with a mocked pymupdf library."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        with patch("app.utils.pdf_extractor.pymupdf") as mock_pymupdf:
            mock_doc = MagicMock()
            mock_doc.page_count = 1
            mock_page = MagicMock()
            mock_page.get_text.return_value = "Test resume content. Python skills."
            mock_doc.__getitem__ = MagicMock(return_value=mock_page)
            mock_pymupdf.open.return_value = mock_doc

            text, error = extract_text_safe(str(pdf_file))

        assert text is not None
        assert error is None
        assert "Test resume content" in text

    def test_corrupted_pdf_returns_error(self, tmp_path):
        """Corrupted PDF should return error, not crash."""
        pdf_file = tmp_path / "corrupt.pdf"
        pdf_file.write_bytes(b"NOT A REAL PDF CONTENT HERE")

        with patch("app.utils.pdf_extractor.pymupdf") as mock_pymupdf:
            mock_pymupdf.open.side_effect = Exception("File corrupted")

            text, error = extract_text_safe(str(pdf_file))

        assert text is None
        assert error is not None
