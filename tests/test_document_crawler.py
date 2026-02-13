"""Tests for document portal crawler (Phase 2b).

All tests are offline — mock HTTP calls.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.document_crawler import (
    _extract_pdf_links,
    _looks_like_pdf_url,
    _should_skip,
    _title_from_url,
)


# ── Tests: _looks_like_pdf_url ───────────────────────────────────


class TestLooksLikePdfUrl:
    def test_pdf_extension(self):
        assert _looks_like_pdf_url("https://example.com/doc.pdf") is True

    def test_pdf_with_query(self):
        assert _looks_like_pdf_url("https://example.com/doc.pdf?token=abc") is True

    def test_download_pattern(self):
        assert _looks_like_pdf_url("https://portal.be/api/download?id=123") is True

    def test_getdocument_pattern(self):
        assert _looks_like_pdf_url("https://portal.be/getDocument/123") is True

    def test_attachment_pattern(self):
        assert _looks_like_pdf_url("https://portal.be/attachment/456") is True

    def test_html_page(self):
        assert _looks_like_pdf_url("https://example.com/page.html") is False

    def test_plain_url(self):
        assert _looks_like_pdf_url("https://example.com/notices/123") is False


# ── Tests: _should_skip ──────────────────────────────────────────


class TestShouldSkip:
    def test_login(self):
        assert _should_skip("https://portal.be/login") is True

    def test_css(self):
        assert _should_skip("https://portal.be/style.css") is True

    def test_javascript(self):
        assert _should_skip("javascript:void(0)") is True

    def test_normal_url(self):
        assert _should_skip("https://portal.be/documents/cahier.pdf") is False


# ── Tests: _extract_pdf_links ────────────────────────────────────


class TestExtractPdfLinks:
    def test_simple_pdf_link(self):
        html = '<html><body><a href="/docs/cahier.pdf">Cahier des charges</a></body></html>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 1
        assert links[0]["url"] == "https://portal.be/docs/cahier.pdf"
        assert links[0]["title"] == "Cahier des charges"

    def test_multiple_pdf_links(self):
        html = """
        <html><body>
            <a href="/docs/lot1.pdf">Lot 1</a>
            <a href="/docs/lot2.pdf">Lot 2</a>
            <a href="/docs/annexe.pdf">Annexe</a>
        </body></html>
        """
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 3

    def test_absolute_url(self):
        html = '<a href="https://other.be/doc.pdf">Doc</a>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert links[0]["url"] == "https://other.be/doc.pdf"

    def test_download_link(self):
        html = '<a href="/api/download?fileId=123&type=pdf">Télécharger</a>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 1

    def test_no_pdf_links(self):
        html = '<html><body><a href="/page.html">Page</a><a href="/about">About</a></body></html>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 0

    def test_deduplication(self):
        html = """
        <a href="/docs/cahier.pdf">Link 1</a>
        <a href="/docs/cahier.pdf">Link 2</a>
        """
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 1

    def test_skips_login_links(self):
        html = '<a href="/login/redirect.pdf">Login</a>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 0

    def test_title_from_attribute(self):
        html = '<a href="/doc.pdf" title="Cahier des charges complet">Download</a>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert links[0]["title"] == "Cahier des charges complet"

    def test_iframe_pdf(self):
        html = '<iframe src="/viewer/cahier.pdf"></iframe>'
        links = _extract_pdf_links(html, "https://portal.be")
        assert len(links) == 1

    def test_real_world_publicprocurement_pattern(self):
        """Simulate a publicprocurement.be page structure."""
        html = """
        <html><body>
        <div class="documents-list">
            <a href="/api/v1/files/abc-123/download/cahier_des_charges.pdf"
               class="document-link" title="Cahier des charges">
                <span>Cahier des charges</span>
            </a>
            <a href="/api/v1/files/def-456/download/annexe_technique.pdf"
               class="document-link" title="Annexe technique">
                <span>Annexe technique</span>
            </a>
            <a href="/publication-workspaces/789/general"
               class="nav-link">
                Retour
            </a>
        </div>
        </body></html>
        """
        links = _extract_pdf_links(html, "https://publicprocurement.be")
        assert len(links) == 2
        assert "cahier_des_charges.pdf" in links[0]["url"]
        assert "annexe_technique.pdf" in links[1]["url"]


# ── Tests: _title_from_url ───────────────────────────────────────


class TestTitleFromUrl:
    def test_pdf_filename(self):
        assert _title_from_url("https://portal.be/docs/cahier-des-charges.pdf") == "cahier des charges"

    def test_underscores(self):
        assert _title_from_url("https://portal.be/annexe_technique.pdf") == "annexe technique"

    def test_no_extension(self):
        assert _title_from_url("https://portal.be/download/12345") == "12345"
