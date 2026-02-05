"""Unit tests for document downloader (mock requests, offline)."""
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.documents.downloader import (
    download_document,
    infer_extension_from_content_type,
    infer_extension_from_file_type_or_url,
)


def test_infer_extension_from_content_type():
    """Infer extension from Content-Type header."""
    assert infer_extension_from_content_type("application/pdf") == "pdf"
    assert infer_extension_from_content_type("text/plain") == "txt"
    assert infer_extension_from_content_type("application/octet-stream") == "bin"
    assert infer_extension_from_content_type(None) == "bin"
    assert infer_extension_from_content_type("application/pdf; charset=utf-8") == "pdf"


def test_infer_extension_from_file_type_or_url():
    """Infer extension from document file_type or URL."""
    assert infer_extension_from_file_type_or_url("PDF", "") == "pdf"
    assert infer_extension_from_file_type_or_url(None, "https://example.com/spec.pdf") == "pdf"
    assert infer_extension_from_file_type_or_url(None, "https://example.com/file.pdf?q=1") == "pdf"
    assert infer_extension_from_file_type_or_url(None, "") == "bin"


def test_download_document_mock_stream(tmp_path):
    """Mock requests.get to return a fake response stream; verify sha256 and file written."""
    fake_content = b"fake pdf content here"
    expected_sha256 = hashlib.sha256(fake_content).hexdigest()
    dest = tmp_path / "downloaded.bin"

    def iter_content(chunk_size=8192):
        yield fake_content

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.iter_content = iter_content
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=None)

    with patch("app.documents.downloader.requests.get", return_value=mock_resp):
        meta = download_document("https://example.com/doc.pdf", dest, timeout_seconds=10)

    assert meta["content_type"] == "application/pdf"
    assert meta["sha256"] == expected_sha256
    assert meta["file_size"] == len(fake_content)
    assert dest.exists()
    assert dest.read_bytes() == fake_content
