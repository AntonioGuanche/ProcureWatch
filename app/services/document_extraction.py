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

    # 1) document-url-lot: external procurement document URLs (cahiers des charges)
    #    These point to buyer platforms (publicprocurement.be, cloud.3p.eu, etc.)
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

    # 2) links: TED-rendered notice PDFs/HTML/XML
    #    Structure per swagger: links.pdf = {lang_code: url, ...}
    #    e.g. links.pdf = {"eng": "https://ted.europa.eu/...", "fra": "https://..."}
    links = raw.get("links")
    if isinstance(links, dict):
        # Priority: pdf > pdfs > html > xml
        for link_key, label, ftype in [
            ("pdf", "Avis TED (PDF)", "PDF"),
            ("pdfs", "Avis TED (PDF)", "PDF"),
            ("html", "Avis TED (HTML)", "HTML"),
            ("xml", "Avis TED (XML)", "XML"),
        ]:
            link_val = links.get(link_key)
            if isinstance(link_val, str) and _is_valid_url(link_val):
                # Simple string URL (legacy format)
                _add(link_val, label, ftype=ftype)
            elif isinstance(link_val, dict):
                # Multilingual dict: {lang_code: url_string}
                # Pick best language: FR > EN > NL > DE > first available
                best_url = None
                best_lang = ""
                for pref_lang in ("fra", "fr", "eng", "en", "nld", "nl", "deu", "de"):
                    candidate = link_val.get(pref_lang)
                    if isinstance(candidate, str) and _is_valid_url(candidate):
                        best_url = candidate
                        best_lang = pref_lang
                        break
                if not best_url:
                    # Take first available
                    for lk, lv in link_val.items():
                        if isinstance(lv, str) and _is_valid_url(lv):
                            best_url = lv
                            best_lang = lk
                            break
                if best_url:
                    _add(best_url, f"{label} [{best_lang}]", best_lang, ftype=ftype)
            elif isinstance(link_val, list):
                # List of URLs
                for entry in link_val:
                    if isinstance(entry, str) and _is_valid_url(entry):
                        _add(entry, label, ftype=ftype)
                    elif isinstance(entry, dict):
                        url = entry.get("url") or entry.get("href") or ""
                        _add(url, label, ftype=ftype)

    # 3) document-url-part and other procurement doc URLs
    for key in ("document-url-part", "procurement-docs-url", "url-participation", "url-tool"):
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


def _extract_bosa_documents(raw: dict[str, Any], notice: Any = None) -> list[dict[str, Any]]:
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

    # 3) Always create a portal link for BOSA notices so users can access
    #    the documents (cahier des charges, DUME, etc.) via the web portal.
    #    The BOSA API does NOT expose document download URLs.
    workspace_id = None
    if notice is not None:
        workspace_id = getattr(notice, "publication_workspace_id", None) or getattr(notice, "source_id", None)
    if not workspace_id:
        workspace_id = raw.get("id") or raw.get("publicationWorkspaceId")

    if workspace_id:
        portal_url = f"https://publicprocurement.be/publication-workspaces/{workspace_id}/general"
        _add(portal_url, "📄 Ouvrir sur e-Procurement (documents, DUME, dépôt)", ftype="HTML")

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
        extracted = _extract_bosa_documents(raw, notice=notice)
    else:
        extracted = _extract_ted_documents(raw) + _extract_bosa_documents(raw, notice=notice)

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
    batch_size: int = 10,
    limit: int = 0,
) -> dict[str, int]:
    """
    Backfill documents for existing notices — ultra-lightweight.

    Processes ONE notice at a time via raw SQL to avoid ORM memory bloat.
    Uses id-based cursor for consistent performance on 100k+ rows.

    Args:
        limit: max notices to process (0 = all)
    """
    from sqlalchemy import text as sql_text
    import json as _json

    stats = {"processed": 0, "documents_created": 0, "notices_with_docs": 0}
    last_id = ""

    source_filter = "AND source = :source" if source else ""

    while True:
        if limit and stats["processed"] >= limit:
            break

        current_limit = min(batch_size, (limit - stats["processed"]) if limit else batch_size)

        # Fetch only IDs first (tiny memory footprint)
        params: dict[str, Any] = {"cursor": last_id, "lim": current_limit}
        if source:
            params["source"] = source

        id_rows = db.execute(sql_text(f"""
            SELECT id FROM notices
            WHERE raw_data IS NOT NULL AND id > :cursor {source_filter}
            ORDER BY id LIMIT :lim
        """), params).fetchall()

        if not id_rows:
            break

        for (notice_id,) in id_rows:
            last_id = notice_id

            # Load raw_data for ONE notice
            row = db.execute(sql_text(
                "SELECT raw_data, source FROM notices WHERE id = :nid"
            ), {"nid": notice_id}).fetchone()

            if not row or not row[0]:
                stats["processed"] += 1
                continue

            raw_data = row[0]
            nsource = row[1]

            # Parse JSON if needed (Postgres JSONB returns dict, but safety check)
            if isinstance(raw_data, str):
                try:
                    raw_data = _json.loads(raw_data)
                except Exception:
                    stats["processed"] += 1
                    continue

            if not isinstance(raw_data, dict):
                stats["processed"] += 1
                continue

            # Extract document URLs from raw_data
            if nsource == "TED_EU":
                docs = _extract_ted_documents(raw_data)
            else:
                docs = _extract_bosa_documents(raw_data)

            if not docs:
                stats["processed"] += 1
                continue

            # Get existing URLs
            existing = set(
                r[0] for r in db.execute(sql_text(
                    "SELECT url FROM notice_documents WHERE notice_id = :nid"
                ), {"nid": notice_id}).fetchall()
            )

            if replace:
                db.execute(sql_text(
                    "DELETE FROM notice_documents WHERE notice_id = :nid"
                ), {"nid": notice_id})
                existing = set()

            created = 0
            for doc in docs:
                url = doc.get("url", "")
                if url in existing:
                    continue
                db.execute(sql_text("""
                    INSERT INTO notice_documents (id, notice_id, title, url, file_type, language)
                    VALUES (:id, :nid, :title, :url, :ftype, :lang)
                """), {
                    "id": str(uuid.uuid4()),
                    "nid": notice_id,
                    "title": (doc.get("title") or "Document")[:500],
                    "url": url[:2000],
                    "ftype": doc.get("file_type"),
                    "lang": doc.get("language"),
                })
                existing.add(url)
                created += 1

            stats["processed"] += 1
            stats["documents_created"] += created
            if created > 0:
                stats["notices_with_docs"] += 1

            # Free raw_data reference
            del raw_data

        # Commit after each micro-batch
        db.commit()

        if stats["processed"] % 500 == 0 and stats["processed"] > 0:
            logger.info(
                "Document backfill progress: processed=%d, created=%d",
                stats["processed"], stats["documents_created"],
            )

    db.commit()
    logger.info(
        "Document backfill done: processed=%d, created=%d, notices_with_docs=%d",
        stats["processed"], stats["documents_created"], stats["notices_with_docs"],
    )
    return stats
