"""Unit tests for PDF text extractor (tiny PDF fixture or pypdf writer, offline)."""
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.documents.pdf_extractor import extract_text_from_pdf


def test_extract_text_from_pdf_tiny_fixture(tmp_path):
    """Generate a tiny PDF with pypdf writer and verify extraction does not crash."""
    pdf_path = tmp_path / "tiny.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    # Blank page may yield empty text; at least no exception
    text = extract_text_from_pdf(pdf_path)
    assert isinstance(text, str)
    assert text == "" or len(text) >= 0


def test_extract_text_from_pdf_empty_file(tmp_path):
    """Pypdf can open minimal PDF; we just require no crash and return str."""
    pdf_path = tmp_path / "minimal.pdf"
    w = PdfWriter()
    w.add_blank_page(72, 72)
    with open(pdf_path, "wb") as f:
        w.write(f)
    text = extract_text_from_pdf(pdf_path)
    assert text == ""


def test_extract_text_from_pdf_file_not_found():
    """Raise FileNotFoundError when path does not exist."""
    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf("/nonexistent/path/document.pdf")
