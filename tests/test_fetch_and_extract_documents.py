"""Ingest tests for fetch_and_extract_documents: mock downloader, verify DB updates (offline)."""
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_fetch_and_extract_documents.db"

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from pypdf import PdfWriter

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.db.models.notice import Notice
from app.db.models.notice_document import NoticeDocument


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_fetch_and_extract_mock_downloader(db_schema, tmp_path):
    """Mock requests.get in downloader to return fake PDF stream; verify NoticeDocument updated and extraction set."""
    db = SessionLocal()
    try:
        n = Notice(
            source="publicprocurement.be",
            source_id="PPP-FAKE-001",
            title="Fake Notice",
            country="BE",
            url="https://example.com/1",
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        notice_id = str(n.id)
        doc = NoticeDocument(
            notice_id=notice_id,
            title="Spec",
            url="https://example.com/spec.pdf",
            file_type="PDF",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = str(doc.id)
    finally:
        db.close()

    # Minimal PDF bytes for fake response
    w = PdfWriter()
    w.add_blank_page(72, 72)
    from io import BytesIO
    pdf_buf = BytesIO()
    w.write(pdf_buf)
    fake_pdf_bytes = pdf_buf.getvalue()

    def fake_iter_content(chunk_size=8192):
        yield fake_pdf_bytes

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.iter_content = fake_iter_content
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=None)

    from ingest import fetch_and_extract_documents
    with patch("app.documents.downloader.requests.get", return_value=mock_resp):
        old_argv = list(sys.argv)
        sys.argv = [
            "fetch_and_extract_documents.py",
            "--notice-id", notice_id,
            "--storage-dir", str(tmp_path / "data" / "documents"),
        ]
        try:
            exit_code = fetch_and_extract_documents.main()
        finally:
            sys.argv = old_argv
        assert exit_code == 0

    db = SessionLocal()
    try:
        doc_after = db.query(NoticeDocument).filter(NoticeDocument.id == doc_id).first()
        assert doc_after is not None
        assert doc_after.local_path is not None
        assert doc_after.download_status == "ok"
        assert doc_after.file_size == len(fake_pdf_bytes)
        assert doc_after.extraction_status == "ok"
        assert doc_after.extracted_text is not None  # may be "" for blank page
    finally:
        db.close()
