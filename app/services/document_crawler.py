"""Phase 2b: BOSA Document Crawler via Official API.

Uses the official BOSA eProcurementDos API (OAuth2 + BelGov-Trace-Id)
to discover and download procurement documents:
  1. GET /publication-workspaces/{id}/documents → list of docs
  2. GET /publication-workspace-document-versions/{version_id}/download-url → presigned S3 URL
  3. Download PDF from presigned URL → extract text → store in notice_documents

Usage:
    from app.services.document_crawler import batch_crawl_notices
    stats = batch_crawl_notices(db, limit=50)
"""
import hashlib
import logging
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

PDF_EXTENSIONS = {".pdf"}
DOWNLOAD_TIMEOUT = 90
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
POLITENESS_DELAY = 0.5  # seconds between API calls
USER_AGENT = "ProcureWatch/1.0 (+https://procurewatch.be)"


# ── BOSA Official API Client ─────────────────────────────────────


def _get_bosa_client():
    """Get official BOSA client with OAuth2 credentials."""
    from app.connectors.bosa.client import _get_client
    from app.connectors.bosa.official_client import OfficialEProcurementClient

    client, provider = _get_client()
    if not isinstance(client, OfficialEProcurementClient):
        raise RuntimeError(f"BOSA client is {provider}, not official")
    return client


def list_workspace_documents(workspace_id: str) -> list[dict[str, Any]]:
    """List documents for a publication workspace via official BOSA API.

    Uses OAuth2 + BelGov-Trace-Id headers (required by BOSA).
    """
    client = _get_bosa_client()
    dos_base = client.dos_base_url.rstrip("/")
    url = f"{dos_base}/publication-workspaces/{workspace_id}/documents?full=false&type=WORKSPACE"

    try:
        resp = client.request("GET", url)
        if resp.status_code in (404, 403):
            logger.debug("Workspace %s: %d", workspace_id, resp.status_code)
            return []
        if resp.status_code != 200:
            logger.warning(
                "Workspace %s documents: status=%d body=%s",
                workspace_id, resp.status_code, resp.text[:200],
            )
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to list docs for workspace %s: %s", workspace_id, e)
        return []


def get_download_url(version_id: str) -> Optional[str]:
    """Get presigned download URL for a document version via official API."""
    client = _get_bosa_client()
    dos_base = client.dos_base_url.rstrip("/")
    url = (
        f"{dos_base}/publication-workspace-document-versions/"
        f"{version_id}/download-url?unpublished=false"
    )

    try:
        resp = client.request("GET", url)
        if resp.status_code in (404, 403):
            return None
        if resp.status_code != 200:
            logger.warning("Download URL for %s: status=%d", version_id, resp.status_code)
            return None
        data = resp.json()
        return data.get("value") if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("Failed to get download URL for version %s: %s", version_id, e)
        return None


# ── Document Processing ───────────────────────────────────────────


def _parse_bosa_document(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Parse a BOSA document JSON into a flat dict."""
    titles = doc_data.get("titles", [])
    title = titles[0]["text"] if titles else None

    versions = doc_data.get("versions", [])
    version = versions[0] if versions else {}
    version_id = version.get("id")

    inner_doc = version.get("document", {})
    original_filename = inner_doc.get("originalFileName", "")
    file_hash = inner_doc.get("fileHash")

    ext = ""
    if original_filename and "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()

    languages = doc_data.get("languages", [])
    lang = languages[0] if languages else None

    return {
        "bosa_doc_id": doc_data.get("id"),
        "workspace_id": doc_data.get("workspaceId"),
        "doc_type": doc_data.get("type"),
        "title": title,
        "original_filename": original_filename,
        "version_id": version_id,
        "file_hash": file_hash,
        "file_extension": ext,
        "language": lang,
        "is_pdf": ext in PDF_EXTENSIONS,
    }


def _download_and_extract(download_url: str, doc_id: str) -> Optional[dict[str, Any]]:
    """Download file from presigned URL, extract text if PDF."""
    from app.documents.pdf_extractor import extract_text_from_pdf

    tmp_dir = Path(tempfile.gettempdir()) / "procurewatch_bosa"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"{doc_id}.pdf"

    try:
        resp = requests.get(
            download_url,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        )
        resp.raise_for_status()

        sha256_hash = hashlib.sha256()
        size = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    sha256_hash.update(chunk)
                    size += len(chunk)
                    f.write(chunk)
                if size > MAX_PDF_SIZE:
                    logger.warning("File too large (%d bytes), skipping", size)
                    tmp_path.unlink(missing_ok=True)
                    return None

        if size < 100:
            tmp_path.unlink(missing_ok=True)
            return None

        text = extract_text_from_pdf(tmp_path)
        content_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip()
            or "application/pdf"
        )

        return {
            "sha256": sha256_hash.hexdigest(),
            "file_size": size,
            "content_type": content_type,
            "extracted_text": text or "",
        }

    except Exception as e:
        logger.warning("Download failed: %s", e)
        return None

    finally:
        tmp_path.unlink(missing_ok=True)


# ── Core Crawler ──────────────────────────────────────────────────


def crawl_bosa_documents(
    db: Session,
    notice_id: str,
    workspace_id: str,
    download_pdfs: bool = True,
) -> list[dict[str, Any]]:
    """Discover and download documents for a BOSA notice via official API.

    Args:
        db: Database session
        notice_id: ProcureWatch notice ID
        workspace_id: BOSA publication workspace ID
        download_pdfs: If True, download PDFs and extract text

    Returns:
        List of result dicts per document.
    """
    results: list[dict[str, Any]] = []

    # Step 1: List documents via official API
    raw_docs = list_workspace_documents(workspace_id)
    if not raw_docs:
        return [{"status": "no_documents", "workspace_id": workspace_id}]

    logger.info("Workspace %s: found %d documents", workspace_id, len(raw_docs))

    # Get existing hashes for dedup
    existing_hashes = set(
        row[0] for row in db.execute(
            sql_text(
                "SELECT sha256 FROM notice_documents "
                "WHERE notice_id = :nid AND sha256 IS NOT NULL"
            ),
            {"nid": notice_id},
        ).fetchall()
    )
    existing_checksums = set(
        row[0] for row in db.execute(
            sql_text(
                "SELECT checksum FROM notice_documents "
                "WHERE notice_id = :nid AND checksum IS NOT NULL"
            ),
            {"nid": notice_id},
        ).fetchall()
    )

    for raw_doc in raw_docs:
        parsed = _parse_bosa_document(raw_doc)
        doc_result: dict[str, Any] = {
            "title": parsed["title"],
            "filename": parsed["original_filename"],
            "type": parsed["file_extension"],
            "language": parsed["language"],
            "is_pdf": parsed["is_pdf"],
        }

        if not parsed["version_id"]:
            doc_result["status"] = "no_version"
            results.append(doc_result)
            continue

        # Dedup by BOSA file hash
        if parsed["file_hash"] and parsed["file_hash"] in existing_checksums:
            doc_result["status"] = "exists_hash"
            results.append(doc_result)
            continue

        # Only download PDFs
        if not parsed["is_pdf"]:
            doc_result["status"] = "skipped_non_pdf"
            results.append(doc_result)
            continue

        if not download_pdfs:
            doc_result["status"] = "discovered"
            results.append(doc_result)
            continue

        # Step 2: Get presigned download URL
        time.sleep(POLITENESS_DELAY)
        download_url = get_download_url(parsed["version_id"])
        if not download_url:
            doc_result["status"] = "no_download_url"
            results.append(doc_result)
            continue

        # Step 3: Download and extract
        doc_db_id = str(uuid.uuid4())
        dl_result = _download_and_extract(download_url, doc_db_id)

        if not dl_result:
            doc_result["status"] = "download_failed"
            results.append(doc_result)
            continue

        # Dedup by SHA256
        if dl_result["sha256"] in existing_hashes:
            doc_result["status"] = "exists_content"
            results.append(doc_result)
            continue

        # Create NoticeDocument entry
        doc_entity = NoticeDocument(
            id=doc_db_id,
            notice_id=notice_id,
            url=download_url.split("?")[0],
            title=parsed["title"] or parsed["original_filename"],
            file_type="PDF",
            language=parsed["language"],
            checksum=parsed["file_hash"],
            content_type=dl_result["content_type"],
            file_size=dl_result["file_size"],
            sha256=dl_result["sha256"],
            downloaded_at=datetime.now(timezone.utc),
            download_status="ok",
            extracted_text=dl_result["extracted_text"],
            extracted_at=datetime.now(timezone.utc),
            extraction_status="ok",
        )
        db.add(doc_entity)
        existing_hashes.add(dl_result["sha256"])
        existing_checksums.add(parsed["file_hash"])

        text_len = len(dl_result["extracted_text"])
        doc_result.update({
            "status": "downloaded",
            "doc_id": doc_db_id,
            "file_size": dl_result["file_size"],
            "text_chars": text_len,
        })
        results.append(doc_result)

    db.commit()
    return results


# ── Batch Crawler ─────────────────────────────────────────────────


def batch_crawl_notices(
    db: Session,
    limit: int = 100,
    source: str = "BOSA_EPROC",
    download_pdfs: bool = True,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Batch crawl BOSA notices to discover and download PDF documents.

    Uses publication_workspace_id stored on each notice to call the
    official BOSA API and list/download documents.
    """
    count_sql = """
        SELECT COUNT(*)
        FROM notices n
        WHERE n.source = :source
        AND n.publication_workspace_id IS NOT NULL
        AND n.publication_workspace_id != ''
        AND NOT EXISTS (
            SELECT 1 FROM notice_documents nd
            WHERE nd.notice_id = n.id
            AND nd.download_status = 'ok'
            AND LOWER(COALESCE(nd.file_type, '')) LIKE '%%pdf%%'
        )
    """
    total_eligible = db.execute(
        sql_text(count_sql), {"source": source}
    ).scalar() or 0

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "dry_run": True,
            "message": (
                f"{total_eligible} {source} notices eligible. "
                f"Set dry_run=false to crawl."
            ),
        }

    fetch_sql = """
        SELECT n.id, n.publication_workspace_id
        FROM notices n
        WHERE n.source = :source
        AND n.publication_workspace_id IS NOT NULL
        AND n.publication_workspace_id != ''
        AND NOT EXISTS (
            SELECT 1 FROM notice_documents nd
            WHERE nd.notice_id = n.id
            AND nd.download_status = 'ok'
            AND LOWER(COALESCE(nd.file_type, '')) LIKE '%%pdf%%'
        )
        ORDER BY n.publication_date DESC NULLS LAST
        LIMIT :lim
    """
    rows = db.execute(
        sql_text(fetch_sql), {"source": source, "lim": limit}
    ).fetchall()

    stats: dict[str, Any] = {
        "total_eligible": total_eligible,
        "notices_processed": 0,
        "workspaces_with_docs": 0,
        "total_docs_found": 0,
        "pdfs_found": 0,
        "pdfs_downloaded": 0,
        "pdfs_with_text": 0,
        "skipped_non_pdf": 0,
        "skipped_existing": 0,
        "errors": 0,
        "dry_run": False,
    }

    for notice_id, workspace_id in rows:
        stats["notices_processed"] += 1

        try:
            results = crawl_bosa_documents(
                db, notice_id, workspace_id, download_pdfs=download_pdfs,
            )

            has_docs = False
            for r in results:
                status = r.get("status", "")
                is_pdf = r.get("is_pdf", False)

                if status == "no_documents":
                    continue

                has_docs = True
                stats["total_docs_found"] += 1

                if is_pdf:
                    stats["pdfs_found"] += 1

                if status == "downloaded":
                    stats["pdfs_downloaded"] += 1
                    if r.get("text_chars", 0) > 50:
                        stats["pdfs_with_text"] += 1
                elif status == "skipped_non_pdf":
                    stats["skipped_non_pdf"] += 1
                elif status in ("exists_hash", "exists_content"):
                    stats["skipped_existing"] += 1
                elif status in ("download_failed", "no_download_url"):
                    stats["errors"] += 1

            if has_docs:
                stats["workspaces_with_docs"] += 1

            time.sleep(POLITENESS_DELAY)

        except Exception as e:
            logger.warning("Crawl error for notice %s: %s", notice_id, e)
            stats["errors"] += 1

    logger.info(
        "Batch crawl: notices=%d workspaces_with_docs=%d "
        "pdfs_found=%d downloaded=%d with_text=%d errors=%d",
        stats["notices_processed"],
        stats["workspaces_with_docs"],
        stats["pdfs_found"],
        stats["pdfs_downloaded"],
        stats["pdfs_with_text"],
        stats["errors"],
    )
    return stats
