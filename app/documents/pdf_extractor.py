"""
Extract text from PDF files using pypdf (pure Python).
"""
from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(path: str | Path) -> str:
    """
    Extract text from a PDF file. Returns concatenated text from all pages.
    If extraction returns no text (e.g. scanned image-only PDF), returns empty string.
    Caller should still mark extraction_status=ok when no exception is raised.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text()
            if text:
                parts.append(text)
        except Exception:
            # Per-page failure: continue with other pages
            continue
    return "\n".join(parts) if parts else ""
