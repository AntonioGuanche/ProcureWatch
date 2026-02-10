"""
Extract document URLs from notice raw_data and persist as NoticeDocument rows.

Supports both TED and BOSA sources.
"""
import logging
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice as Notice
from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)


# ── Extraction helpers ─────────────────────────────────────────────


def _is_valid_url(url: Any) -> bool:
    """Check if value looks like a valid URL."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _guess_file_type(url: str) -> Optional[str]:
    """Guess file type from URL extension."""
    lower = url.lower().split("?")[0]
    for ext, ft in [
        (".pdf", "PDF"), (".doc", "DOC"), (".docx", "DOCX"),
        (".xls", "XLS"), (".xlsx", "XLSX"),
        (".zip", "ZIP"), (".rar", "RAR"),
        (".xml", "XML"), (".html", "HTML"), (".htm", "HTML"),
        (".odt", "ODT"), (".ods", "ODS"),
        (".csv", "CSV"), (".txt", "TXT"),
    ]:
        if lower.endswith(ext):
            return ft
    return None


def _extract_ted_documents(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract document URLs from TED notice raw_data."""
    docs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _add(url: str, title: str = "", lang: str = "", ftype: str = ""):
        url = url.strip()
        if url in seen_urls or not _is_valid_url(url):
            return
        seen_urls.add(url)
        docs.append({
            "url": url,
            "title": title or _title_from_url(url),
            "language": lang[:10] if lang else None,
            "file_type": ftype or _guess_file_type(url),
        })

    # 1) document-url-lot: string or list of strings/dicts
    doc_url_lot = raw.get("document-url-lot")
    if isinstance(doc_url_lot, str):
        _add(doc_url_lot, "Documents du marché")
    elif isinstance(doc_url_lot, list):
        for entry in doc_url_lot:
            if isinstance(entry, str):
                _add(entry, "Documents du marché")
            elif isinstance(entry, dict):
                url = entry.get("url") or entry.get("href") or entry.get("value") or ""
                lang = entry.get("language") or entry.get("lang") or ""
                _add(url, entry.get("title") or "Documents du marché", lang)

    # 2) links: dict with html/xml/pdf keys, or list
    links = raw.get("links")
    if isinstance(links, dict):
        for key in ("html", "xml", "pdf"):
            url = links.get(key)
            if isinstance(url, str):
                _add(url, f"Avis TED ({key.upper()})", ftype=key.upper())
    elif isinstance(links, list):
        for entry in links:
            if isinstance(entry, str):
                _add(entry, "Avis TED")
            elif isinstance(entry, dict):
                url = entry.get("url") or entry.get("href") or ""
                _add(url, entry.get("title") or "Avis TED")

    # 3) procurement-docs-url (sometimes present)
    for key in ("procurement-docs-url", "url-participation", "url-tool"):
        val = raw.get(key)
        if isinstance(val, str) and _is_valid_url(val):
            _add(val, _doc_label(key))
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and _is_valid_url(v):
                    _add(v, _doc_label(key))
                elif isinstance(v, dict):
                    url = v.get("url") or v.get("href") or v.get("value") or ""
                    _add(url, v.get("title") or _doc_label(key))

    return docs


def _extract_bosa_documents(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract document URLs from BOSA notice raw_data."""
    docs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _add(url: str, title: str = "", lang: str = "", ftype: str = ""):
        url = url.strip()
        if url in seen_urls or not _is_valid_url(url):
            return
        seen_urls.add(url)
        docs.append({
            "url": url,
            "title": title or _title_from_url(url),
            "language": lang[:10] if lang else None,
            "file_type": ftype or _guess_file_type(url),
        })

    # BOSA raw_data may have documents in various places
    # 1) "documents" or "attachments" list
    for key in ("documents", "attachments", "files"):
        items = raw.get(key)
        if isinstance(items, list):
            for doc in items:
                if isinstance(doc, dict):
                    url = (
                        doc.get("downloadUrl") or doc.get("url")
                        or doc.get("href") or doc.get("link") or ""
                    )
                    title = (
                        doc.get("name") or doc.get("title")
                        or doc.get("fileName") or doc.get("description") or ""
                    )
                    lang = doc.get("language") or ""
                    ftype = doc.get("type") or doc.get("mimeType") or ""
                    _add(url, title, lang, ftype)

    # 2) Dossier documents
    dossier = raw.get("dossier")
    if isinstance(dossier, dict):
        for key in ("documents", "attachments"):
            items = dossier.get(key)
            if isinstance(items, list):
                for doc in items:
                    if isinstance(doc, dict):
                        url = doc.get("downloadUrl") or doc.get("url") or ""
                        title = doc.get("name") or doc.get("title") or ""
                        _add(url, title, doc.get("language", ""))

    # 3) The notice URL itself as a document link
    notice_url = raw.get("url")
    if isinstance(notice_url, str) and _is_valid_url(notice_url):
        _add(notice_url, "Avis sur e-Procurement", ftype="HTML")

    return docs


def _title_from_url(url: str) -> str:
    """Extract a title from URL filename."""
    try:
        path = urlparse(url).path
        name = path.rsplit("/", 1)[-1] if "/" in path else ""
        if name and "." in name:
            return name[:200]
    except Exception:
        pass
    return "Document"


def _doc_label(key: str) -> str:
    """Human label for TED document keys."""
    labels = {
        "procurement-docs-url": "Documents de marché",
        "url-participation": "Lien de participation",
        "url-tool": "Outil de soumission",
    }
    return labels.get(key, "Document")


# ── Persistence ────────────────────────────────────────────────────


def extract_and_save_documents(
    db: Session,
    notice: Notice,
    replace: bool = False,
) -> int:
    """
    Extract documents from notice.raw_data and save as NoticeDocument rows.

    Args:
        db: Database session.
        notice: Notice with raw_data.
        replace: If True, delete existing documents first.

    Returns:
        Number of documents created.
    """
    raw = notice.raw_data
    if not isinstance(raw, dict):
        return 0

    source = (notice.source or "").upper()

    if "TED" in source:
        extracted = _extract_ted_documents(raw)
    elif "BOSA" in source:
        extracted = _extract_bosa_documents(raw)
    else:
        extracted = _extract_ted_documents(raw) + _extract_bosa_documents(raw)

    if not extracted:
        return 0

    if replace:
        db.query(NoticeDocument).filter(
            NoticeDocument.notice_id == notice.id
        ).delete()

    # Check existing URLs to avoid duplicates
    existing_urls = set()
    if not replace:
        existing = (
            db.query(NoticeDocument.url)
            .filter(NoticeDocument.notice_id == notice.id)
            .all()
        )
        existing_urls = {row[0] for row in existing}

    count = 0
    for doc in extracted:
        if doc["url"] in existing_urls:
            continue
        db.add(NoticeDocument(
            id=str(uuid.uuid4()),
            notice_id=notice.id,
            title=(doc.get("title") or "Document")[:500],
            url=doc["url"][:2000],
            file_type=doc.get("file_type"),
            language=doc.get("language"),
        ))
        existing_urls.add(doc["url"])
        count += 1

    return count


def backfill_documents_for_all(
    db: Session,
    source: Optional[str] = None,
    replace: bool = False,
    batch_size: int = 200,
) -> dict[str, int]:
    """
    Backfill documents for all existing notices.

    Returns:
        {"processed": N, "documents_created": N, "notices_with_docs": N}
    """
    query = db.query(Notice).filter(Notice.raw_data.isnot(None))
    if source:
        query = query.filter(Notice.source == source)

    stats = {"processed": 0, "documents_created": 0, "notices_with_docs": 0}
    offset = 0

    while True:
        batch = query.offset(offset).limit(batch_size).all()
        if not batch:
            break

        for notice in batch:
            count = extract_and_save_documents(db, notice, replace=replace)
            stats["processed"] += 1
            stats["documents_created"] += count
            if count > 0:
                stats["notices_with_docs"] += 1

        db.flush()
        offset += batch_size

    db.commit()
    logger.info(
        "Document backfill: processed=%d, created=%d, notices_with_docs=%d",
        stats["processed"], stats["documents_created"], stats["notices_with_docs"],
    )
    return stats
