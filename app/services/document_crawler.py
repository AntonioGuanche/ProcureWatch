"""Phase 2b: Document Portal Crawler.

Follows HTML links (publicprocurement.be portals, TED document-url-lot pages,
e-tendering platforms) to discover actual PDF documents for download.

Strategy used by competing platforms:
  1. Fetch the portal/HTML page linked in notice_documents
  2. Parse HTML for PDF links (<a href="...pdf">, download buttons, etc.)
  3. Create new NoticeDocument entries for discovered PDFs
  4. Download + extract text (reuses existing pipeline)

Usage:
    from app.services.document_crawler import crawl_portal_for_pdfs, batch_crawl_notices

    # Single notice
    new_docs = crawl_portal_for_pdfs(db, notice_id, portal_url)

    # Batch: all notices with portal links but no PDF docs
    stats = batch_crawl_notices(db, limit=200, source="BOSA_EPROC")
"""
import hashlib
import logging
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

# Timeout for fetching portal pages
PAGE_FETCH_TIMEOUT = 30

# Timeout for downloading individual PDFs
PDF_DOWNLOAD_TIMEOUT = 60

# Max PDF file size (50 MB)
MAX_PDF_SIZE = 50 * 1024 * 1024

# Max PDFs to discover per portal page
MAX_PDFS_PER_PAGE = 20

# Delay between requests to same domain (seconds)
POLITENESS_DELAY = 1.0

# User-Agent to identify ourselves
USER_AGENT = (
    "ProcureWatch/1.0 (Procurement monitoring platform; "
    "+https://procurewatch.be) Python-requests"
)

# Domains we know host procurement documents
KNOWN_PROCUREMENT_DOMAINS = {
    "publicprocurement.be",
    "enot.publicprocurement.be",
    "ted.europa.eu",
    "etendering.ted.europa.eu",
    "eten.publicprocurement.be",
}

# URL patterns that are NOT actual documents (navigation, auth, etc.)
SKIP_URL_PATTERNS = [
    r"/login",
    r"/auth",
    r"/register",
    r"/account",
    r"javascript:",
    r"mailto:",
    r"tel:",
    r"#$",
    r"\.css",
    r"\.js$",
    r"\.ico$",
    r"\.svg$",
    r"\.png$",
    r"\.jpg$",
    r"\.gif$",
]


# ── HTML Parsing ──────────────────────────────────────────────────


def _fetch_page(url: str) -> Optional[str]:
    """Fetch HTML page content. Returns None on failure."""
    try:
        resp = requests.get(
            url,
            timeout=PAGE_FETCH_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-BE,fr;q=0.9,nl;q=0.8,en;q=0.7",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()

        # Only process HTML responses
        ct = resp.headers.get("Content-Type", "")
        if "html" not in ct and "xml" not in ct and "text" not in ct:
            logger.debug("Non-HTML response (%s) for %s", ct, url)
            return None

        return resp.text

    except Exception as e:
        logger.warning("Failed to fetch portal page %s: %s", url[:120], e)
        return None


def _extract_pdf_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Parse HTML and extract PDF download links.

    Returns list of {"url": ..., "title": ...} dicts.
    """
    from html.parser import HTMLParser

    pdf_links: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    class LinkExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._current_tag = ""
            self._current_attrs: dict = {}
            self._link_text = ""
            self._in_a = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            self._current_tag = tag
            self._current_attrs = attrs_dict

            if tag == "a":
                self._in_a = True
                self._link_text = ""

            # Direct PDF link in <a href>
            href = attrs_dict.get("href", "")
            if href and _looks_like_pdf_url(href):
                abs_url = urljoin(base_url, href)
                if abs_url not in seen_urls and not _should_skip(abs_url):
                    seen_urls.add(abs_url)
                    # Title from various attributes
                    title = (
                        attrs_dict.get("title")
                        or attrs_dict.get("aria-label")
                        or attrs_dict.get("download")
                        or ""
                    )
                    pdf_links.append({"url": abs_url, "title": title})

            # Also check for download links with explicit type
            if attrs_dict.get("type", "").lower() == "application/pdf":
                abs_url = urljoin(base_url, href)
                if abs_url not in seen_urls:
                    seen_urls.add(abs_url)
                    pdf_links.append({
                        "url": abs_url,
                        "title": attrs_dict.get("title", ""),
                    })

            # <iframe> or <embed> pointing to PDFs
            if tag in ("iframe", "embed", "object"):
                src = attrs_dict.get("src") or attrs_dict.get("data") or ""
                if src and _looks_like_pdf_url(src):
                    abs_url = urljoin(base_url, src)
                    if abs_url not in seen_urls:
                        seen_urls.add(abs_url)
                        pdf_links.append({"url": abs_url, "title": ""})

        def handle_data(self, data):
            if self._in_a:
                self._link_text += data.strip()

        def handle_endtag(self, tag):
            if tag == "a":
                self._in_a = False
                # Update title with link text if we found one
                if self._link_text and pdf_links:
                    last = pdf_links[-1]
                    if not last["title"]:
                        last["title"] = self._link_text[:200]

    try:
        parser = LinkExtractor()
        parser.feed(html)
    except Exception as e:
        logger.warning("HTML parsing error: %s", e)

    return pdf_links[:MAX_PDFS_PER_PAGE]


def _looks_like_pdf_url(url: str) -> bool:
    """Check if URL likely points to a PDF document."""
    url_lower = url.lower().strip()

    # Direct .pdf extension
    if ".pdf" in url_lower:
        return True

    # Common download patterns
    download_patterns = [
        r"/download",
        r"/getdocument",
        r"/getfile",
        r"/attachment",
        r"/telecharger",
        r"action=download",
        r"type=pdf",
        r"format=pdf",
        r"contenttype=pdf",
    ]
    return any(p in url_lower for p in download_patterns)


def _should_skip(url: str) -> bool:
    """Check if URL should be skipped (not a document)."""
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in SKIP_URL_PATTERNS)


def _title_from_url(url: str) -> str:
    """Generate a title from a URL path."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    filename = path.split("/")[-1] if path else ""

    # Clean up filename
    if filename:
        # Remove extension
        name = filename.rsplit(".", 1)[0] if "." in filename else filename
        # Replace separators
        name = name.replace("-", " ").replace("_", " ")
        return name[:200]

    return "Document"


# ── Download Pipeline ─────────────────────────────────────────────


def _download_pdf(url: str, doc_id: str) -> Optional[dict]:
    """Download PDF to /tmp, extract text, return metadata. Deletes file after."""
    from app.documents.pdf_extractor import extract_text_from_pdf

    tmp_dir = Path(tempfile.gettempdir()) / "procurewatch_crawl"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"{doc_id}.pdf"

    try:
        resp = requests.get(
            url,
            timeout=PDF_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        )
        resp.raise_for_status()

        # Check content type
        ct = resp.headers.get("Content-Type", "").lower()
        if "html" in ct:
            # It's actually an HTML page, not a PDF
            logger.debug("URL %s returned HTML, not PDF", url[:100])
            return None

        sha256_hash = hashlib.sha256()
        size = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    sha256_hash.update(chunk)
                    size += len(chunk)
                    f.write(chunk)
                if size > MAX_PDF_SIZE:
                    logger.warning("PDF too large (%d bytes): %s", size, url[:100])
                    tmp_path.unlink(missing_ok=True)
                    return None

        if size < 100:
            # Too small to be a real PDF
            tmp_path.unlink(missing_ok=True)
            return None

        # Verify it's actually a PDF
        with open(tmp_path, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            logger.debug("File is not a PDF (header: %s): %s", header[:10], url[:100])
            tmp_path.unlink(missing_ok=True)
            return None

        # Extract text
        text = extract_text_from_pdf(tmp_path)

        return {
            "sha256": sha256_hash.hexdigest(),
            "file_size": size,
            "content_type": ct.split(";")[0].strip() or "application/pdf",
            "extracted_text": text or "",
        }

    except Exception as e:
        logger.warning("Download failed for %s: %s", url[:100], e)
        return None

    finally:
        tmp_path.unlink(missing_ok=True)


# ── Core Crawler ──────────────────────────────────────────────────


def crawl_portal_for_pdfs(
    db: Session,
    notice_id: str,
    portal_url: str,
    download: bool = True,
) -> list[dict[str, Any]]:
    """Crawl a portal page and discover PDF documents.

    Args:
        db: Database session
        notice_id: Notice ID to associate documents with
        portal_url: URL of the portal page to crawl
        download: If True, download + extract PDFs. If False, just discover links.

    Returns:
        List of discovered document dicts with status.
    """
    import time

    results: list[dict[str, Any]] = []

    # Step 1: Fetch portal page
    html = _fetch_page(portal_url)
    if not html:
        return [{"status": "error", "message": f"Could not fetch portal page: {portal_url}"}]

    # Step 2: Extract PDF links
    pdf_links = _extract_pdf_links(html, portal_url)
    if not pdf_links:
        return [{"status": "no_pdfs", "message": f"No PDF links found on {portal_url}"}]

    logger.info("Found %d PDF links on %s", len(pdf_links), portal_url[:100])

    # Step 3: Check which ones we already have
    existing_urls = set(
        row[0] for row in
        db.execute(
            sql_text("SELECT url FROM notice_documents WHERE notice_id = :nid"),
            {"nid": notice_id},
        ).fetchall()
    )

    for link in pdf_links:
        url = link["url"]
        title = link.get("title") or _title_from_url(url)

        if url in existing_urls:
            results.append({"url": url, "title": title, "status": "exists"})
            continue

        # Create NoticeDocument entry
        doc_id = str(uuid.uuid4())
        doc = NoticeDocument(
            id=doc_id,
            notice_id=notice_id,
            url=url,
            title=title[:500] if title else "Document PDF",
            file_type="PDF",
        )

        if download:
            # Politeness delay
            time.sleep(POLITENESS_DELAY)

            # Download and extract
            dl_result = _download_pdf(url, doc_id)
            if dl_result:
                doc.sha256 = dl_result["sha256"]
                doc.file_size = dl_result["file_size"]
                doc.content_type = dl_result["content_type"]
                doc.downloaded_at = datetime.now(timezone.utc)
                doc.download_status = "ok"
                doc.extracted_text = dl_result["extracted_text"]
                doc.extracted_at = datetime.now(timezone.utc)
                doc.extraction_status = "ok"

                # Check dedup by sha256
                existing_sha = db.execute(
                    sql_text(
                        "SELECT id FROM notice_documents "
                        "WHERE notice_id = :nid AND sha256 = :sha"
                    ),
                    {"nid": notice_id, "sha": dl_result["sha256"]},
                ).fetchone()
                if existing_sha:
                    results.append({
                        "url": url, "title": title,
                        "status": "duplicate_content",
                        "sha256": dl_result["sha256"],
                    })
                    continue

                text_len = len(dl_result["extracted_text"])
                results.append({
                    "url": url, "title": title, "doc_id": doc_id,
                    "status": "downloaded",
                    "file_size": dl_result["file_size"],
                    "text_chars": text_len,
                })
            else:
                doc.download_status = "failed"
                doc.download_error = "Download failed or not a valid PDF"
                results.append({
                    "url": url, "title": title, "doc_id": doc_id,
                    "status": "download_failed",
                })
        else:
            results.append({
                "url": url, "title": title, "doc_id": doc_id,
                "status": "discovered",
            })

        db.add(doc)

    db.commit()
    return results


# ── Batch Crawler ─────────────────────────────────────────────────


def batch_crawl_notices(
    db: Session,
    limit: int = 100,
    source: Optional[str] = None,
    download: bool = True,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Crawl portal pages for multiple notices to discover PDF documents.

    Targets notices that have HTML portal links but few/no PDF documents.

    Args:
        db: Database session
        limit: Max notices to process
        source: Filter by notice source (BOSA_EPROC, TED_EU)
        download: If True, download discovered PDFs
        dry_run: If True, just count eligible notices

    Returns:
        Stats dict
    """
    # Find notices with portal/HTML docs but no downloaded PDFs
    # A notice is eligible if:
    #   - It has at least one HTML document (portal link)
    #   - It has no documents with download_status='ok' and file_type containing 'pdf'
    where_source = "AND n.source = :source" if source else ""

    count_sql = f"""
        SELECT COUNT(DISTINCT n.id)
        FROM notices n
        JOIN notice_documents nd_html ON nd_html.notice_id = n.id
            AND (
                LOWER(nd_html.file_type) = 'html'
                OR nd_html.url LIKE '%publicprocurement.be%'
                OR nd_html.url LIKE '%e-tendering%'
                OR nd_html.url LIKE '%etendering%'
            )
        WHERE NOT EXISTS (
            SELECT 1 FROM notice_documents nd_pdf
            WHERE nd_pdf.notice_id = n.id
            AND nd_pdf.download_status = 'ok'
            AND LOWER(COALESCE(nd_pdf.file_type, '')) LIKE '%pdf%'
        )
        {where_source}
    """
    params: dict[str, Any] = {}
    if source:
        params["source"] = source

    total_eligible = db.execute(sql_text(count_sql), params).scalar() or 0

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "dry_run": True,
            "message": f"{total_eligible} notices have portal links but no downloaded PDFs. "
                       f"Set dry_run=false to crawl them.",
        }

    # Fetch eligible notice + portal URL pairs
    fetch_sql = f"""
        SELECT DISTINCT n.id, nd_html.url
        FROM notices n
        JOIN notice_documents nd_html ON nd_html.notice_id = n.id
            AND (
                LOWER(nd_html.file_type) = 'html'
                OR nd_html.url LIKE '%publicprocurement.be%'
                OR nd_html.url LIKE '%e-tendering%'
                OR nd_html.url LIKE '%etendering%'
            )
        WHERE NOT EXISTS (
            SELECT 1 FROM notice_documents nd_pdf
            WHERE nd_pdf.notice_id = n.id
            AND nd_pdf.download_status = 'ok'
            AND LOWER(COALESCE(nd_pdf.file_type, '')) LIKE '%pdf%'
        )
        {where_source}
        ORDER BY n.publication_date DESC NULLS LAST
        LIMIT :lim
    """
    params["lim"] = limit

    rows = db.execute(sql_text(fetch_sql), params).fetchall()

    stats: dict[str, Any] = {
        "total_eligible": total_eligible,
        "notices_processed": 0,
        "pages_fetched": 0,
        "pdfs_discovered": 0,
        "pdfs_downloaded": 0,
        "pdfs_with_text": 0,
        "errors": 0,
        "skipped_existing": 0,
        "dry_run": False,
    }

    for notice_id, portal_url in rows:
        stats["notices_processed"] += 1

        try:
            results = crawl_portal_for_pdfs(
                db, notice_id, portal_url, download=download
            )
            stats["pages_fetched"] += 1

            for r in results:
                status = r.get("status", "")
                if status == "downloaded":
                    stats["pdfs_downloaded"] += 1
                    stats["pdfs_discovered"] += 1
                    if r.get("text_chars", 0) > 50:
                        stats["pdfs_with_text"] += 1
                elif status == "discovered":
                    stats["pdfs_discovered"] += 1
                elif status == "exists" or status == "duplicate_content":
                    stats["skipped_existing"] += 1
                elif status == "download_failed":
                    stats["pdfs_discovered"] += 1
                    stats["errors"] += 1
                elif status == "error":
                    stats["errors"] += 1

        except Exception as e:
            logger.warning("Crawl error for notice %s: %s", notice_id, e)
            stats["errors"] += 1

    logger.info(
        "Batch crawl: processed=%d pages=%d discovered=%d downloaded=%d text=%d errors=%d",
        stats["notices_processed"],
        stats["pages_fetched"],
        stats["pdfs_discovered"],
        stats["pdfs_downloaded"],
        stats["pdfs_with_text"],
        stats["errors"],
    )
    return stats
