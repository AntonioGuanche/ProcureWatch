"""Tests for document analysis service (Phase 2).

All tests are offline — mock HTTP calls and Claude API.
"""
import json
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.services.document_analysis import (
    _build_analysis_prompt,
    _download_and_extract_text,
    _is_pdf_document,
    _parse_cached,
    ensure_extracted_text,
    batch_download_and_extract,
    MAX_ANALYSIS_TEXT,
)


# ── Helpers ───────────────────────────────────────────────────────


def _make_doc(**kwargs):
    """Create a mock NoticeDocument."""
    doc = MagicMock()
    doc.id = kwargs.get("id", "doc-001")
    doc.notice_id = kwargs.get("notice_id", "notice-001")
    doc.url = kwargs.get("url", "https://example.com/cahier.pdf")
    doc.file_type = kwargs.get("file_type", "PDF")
    doc.extracted_text = kwargs.get("extracted_text", None)
    doc.ai_analysis = kwargs.get("ai_analysis", None)
    doc.ai_analysis_generated_at = kwargs.get("ai_analysis_generated_at", None)
    doc.download_status = kwargs.get("download_status", None)
    doc.sha256 = None
    doc.file_size = None
    doc.content_type = None
    doc.downloaded_at = None
    doc.download_error = None
    doc.extracted_at = None
    doc.extraction_status = None
    doc.extraction_error = None
    return doc


def _make_notice(**kwargs):
    """Create a mock ProcurementNotice."""
    notice = MagicMock()
    notice.title = kwargs.get("title", "Travaux de rénovation école primaire")
    notice.cpv_main_code = kwargs.get("cpv_main_code", "45214200")
    notice.organisation_names = kwargs.get(
        "organisation_names", {"fr": "Commune de Namur"}
    )
    notice.estimated_value = kwargs.get("estimated_value", 500000.0)
    notice.deadline = kwargs.get("deadline", datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    notice.nuts_codes = kwargs.get("nuts_codes", ["BE352"])
    return notice


# ── Tests: _is_pdf_document ──────────────────────────────────────


class TestIsPdfDocument:
    def test_pdf_file_type(self):
        doc = _make_doc(file_type="PDF")
        assert _is_pdf_document(doc) is True

    def test_pdf_url(self):
        doc = _make_doc(file_type=None, url="https://example.com/spec.pdf")
        assert _is_pdf_document(doc) is True

    def test_pdf_url_with_query(self):
        doc = _make_doc(file_type=None, url="https://example.com/spec.pdf?token=abc")
        assert _is_pdf_document(doc) is True

    def test_non_pdf(self):
        doc = _make_doc(file_type="HTML", url="https://example.com/page.html")
        assert _is_pdf_document(doc) is False

    def test_none_values(self):
        doc = _make_doc(file_type=None, url="https://example.com/page")
        assert _is_pdf_document(doc) is False


# ── Tests: _build_analysis_prompt ────────────────────────────────


class TestBuildAnalysisPrompt:
    def test_prompt_includes_text(self):
        notice = _make_notice()
        prompt = _build_analysis_prompt("Voici le texte du cahier des charges", notice)
        assert "Voici le texte du cahier des charges" in prompt
        assert "Commune de Namur" in prompt
        assert "45214200" in prompt

    def test_prompt_truncates_long_text(self):
        long_text = "x" * (MAX_ANALYSIS_TEXT + 5000)
        notice = _make_notice()
        prompt = _build_analysis_prompt(long_text, notice)
        assert "[... texte tronqué ...]" in prompt
        # Prompt shouldn't be much longer than max
        assert len(prompt) < MAX_ANALYSIS_TEXT + 5000

    def test_prompt_json_structure(self):
        notice = _make_notice()
        prompt = _build_analysis_prompt("text", notice, lang="fr")
        # Check expected JSON keys in prompt
        for key in [
            "objet", "lots", "criteres_attribution",
            "conditions_participation", "budget", "calendrier",
            "points_attention", "score_accessibilite_pme",
        ]:
            assert f'"{key}"' in prompt

    def test_prompt_nl(self):
        notice = _make_notice()
        prompt = _build_analysis_prompt("text", notice, lang="nl")
        assert "Antwoord in het Nederlands" in prompt

    def test_prompt_missing_notice_fields(self):
        notice = _make_notice(
            title=None, cpv_main_code=None, organisation_names=None,
            estimated_value=None, deadline=None,
        )
        prompt = _build_analysis_prompt("text", notice)
        assert "pas de métadonnées" in prompt


# ── Tests: _parse_cached ─────────────────────────────────────────


class TestParseCached:
    def test_valid_json(self):
        analysis = json.dumps({"objet": "Travaux de toiture", "lots": None})
        doc = _make_doc(
            ai_analysis=analysis,
            ai_analysis_generated_at=datetime(2026, 2, 13, tzinfo=timezone.utc),
        )
        result = _parse_cached(doc)
        assert result["status"] == "ok"
        assert result["analysis"]["objet"] == "Travaux de toiture"
        assert result["cached"] is True

    def test_json_in_markdown_fences(self):
        analysis = '```json\n{"objet": "Test"}\n```'
        doc = _make_doc(
            ai_analysis=analysis,
            ai_analysis_generated_at=datetime(2026, 2, 13, tzinfo=timezone.utc),
        )
        result = _parse_cached(doc)
        assert result["status"] == "ok"
        assert result["analysis"]["objet"] == "Test"

    def test_raw_text_fallback(self):
        doc = _make_doc(
            ai_analysis="Not valid JSON, just free text analysis.",
            ai_analysis_generated_at=datetime(2026, 2, 13, tzinfo=timezone.utc),
        )
        result = _parse_cached(doc)
        assert result["status"] == "ok"
        assert "raw_text" in result["analysis"]

    def test_empty_analysis(self):
        doc = _make_doc(ai_analysis="", ai_analysis_generated_at=None)
        result = _parse_cached(doc)
        assert result["status"] == "ok"
        assert "raw_text" in result["analysis"]


# ── Tests: ensure_extracted_text ─────────────────────────────────


class TestEnsureExtractedText:
    def test_returns_existing_text(self):
        doc = _make_doc(extracted_text="Already extracted text here")
        db = MagicMock()
        result = ensure_extracted_text(db, doc)
        assert result == "Already extracted text here"

    def test_non_pdf_returns_none(self):
        doc = _make_doc(file_type="HTML", url="https://example.com/page.html", extracted_text=None)
        db = MagicMock()
        result = ensure_extracted_text(db, doc)
        assert result is None

    def test_portal_link_returns_none(self):
        doc = _make_doc(
            url="https://publicprocurement.be/publication-workspaces/123/general",
            extracted_text=None,
        )
        db = MagicMock()
        result = ensure_extracted_text(db, doc)
        assert result is None

    @patch("app.services.document_analysis._download_and_extract_text")
    def test_calls_download_for_pdf(self, mock_download):
        mock_download.return_value = "Extracted PDF content"
        doc = _make_doc(extracted_text=None)
        db = MagicMock()
        result = ensure_extracted_text(db, doc)
        assert result == "Extracted PDF content"
        mock_download.assert_called_once_with(doc)


# ── Tests: _download_and_extract_text ────────────────────────────


class TestDownloadAndExtract:
    @patch("app.documents.pdf_extractor.extract_text_from_pdf")
    @patch("requests.get")
    def test_success(self, mock_get, mock_extract):
        fake_pdf = b"%PDF-1.4 fake content here"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.iter_content.return_value = [fake_pdf]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=None)
        mock_get.return_value = mock_resp

        mock_extract.return_value = "Cahier des charges - Article 1"

        doc = _make_doc()
        result = _download_and_extract_text(doc)

        assert result == "Cahier des charges - Article 1"
        assert doc.download_status == "ok"
        assert doc.extraction_status == "ok"
        assert doc.sha256 == hashlib.sha256(fake_pdf).hexdigest()
        assert doc.file_size == len(fake_pdf)

    @patch("requests.get")
    def test_download_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")

        doc = _make_doc()
        result = _download_and_extract_text(doc)

        assert result is None
        assert doc.download_status == "failed"
        assert "Connection refused" in (doc.download_error or "")

    @patch("app.documents.pdf_extractor.extract_text_from_pdf")
    @patch("requests.get")
    def test_empty_pdf(self, mock_get, mock_extract):
        """Scanned PDF with no extractable text."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.iter_content.return_value = [b"fake"]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=None)
        mock_get.return_value = mock_resp

        mock_extract.return_value = ""  # No text from scanned PDF

        doc = _make_doc()
        result = _download_and_extract_text(doc)

        assert result == ""
        assert doc.extraction_status == "ok"
        assert doc.extracted_text == ""
