"""Document pipeline, stats, BOSA document crawler."""
import logging
import re
import traceback
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_admin_key, rate_limit_admin
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["documents"],
    dependencies=[Depends(require_admin_key), Depends(rate_limit_admin)],
)

# ── Phase 2: Document Pipeline ───────────────────────────────────


@router.post(
    "/batch-download-documents",
    tags=["admin"],
    summary="Batch download PDFs and extract text",
    description=(
        "Downloads PDF documents to /tmp, extracts text with pypdf, "
        "stores extracted_text in notice_documents, deletes file.\n\n"
        "Only processes PDF documents that haven't been extracted yet.\n"
        "Use dry_run=true first to see count."
    ),
)
def batch_download_documents(
    limit: int = Query(100, ge=1, le=5000, description="Max documents to process"),
    source: Optional[str] = Query(None, description="Filter: BOSA_EPROC or TED_EU"),
    dry_run: bool = Query(True, description="Preview only"),
    db: Session = Depends(get_db),
) -> dict:
    """Batch download PDFs and extract text (Phase 2 document pipeline)."""
    from app.services.document_analysis import batch_download_and_extract
    return batch_download_and_extract(db, limit=limit, source=source, dry_run=dry_run)


@router.post(
    "/backfill-ted-documents",
    tags=["admin"],
    summary="Re-extract document URLs from TED raw_data (after links fix)",
    description=(
        "Re-runs document extraction on TED notices to pick up links.pdf URLs "
        "that were previously missed due to nested dict parsing bug.\n\n"
        "For limit <= 2000: synchronous (returns results).\n"
        "For limit > 2000: background task (returns immediately).\n"
        "Use replace=true to delete old docs and re-extract from scratch."
    ),
)
def backfill_ted_documents(
    limit: int = Query(1000, ge=1, le=200000, description="Max notices to process"),
    replace: bool = Query(False, description="Delete existing docs and re-extract"),
    dry_run: bool = Query(True, description="Preview only"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
) -> dict:
    """Backfill TED documents from raw_data with corrected extraction."""
    from sqlalchemy import text as sql_text
    from app.services.document_extraction import backfill_documents_for_all

    if dry_run:
        total = db.execute(sql_text(
            "SELECT COUNT(*) FROM notices WHERE source = 'TED_EU' AND raw_data IS NOT NULL"
        )).scalar() or 0
        current_docs = db.execute(sql_text("""
            SELECT COUNT(*) FROM notice_documents nd
            JOIN notices n ON n.id = nd.notice_id
            WHERE n.source = 'TED_EU'
        """)).scalar() or 0
        ted_pdf_docs = db.execute(sql_text("""
            SELECT COUNT(*) FROM notice_documents nd
            JOIN notices n ON n.id = nd.notice_id
            WHERE n.source = 'TED_EU'
              AND nd.url LIKE '%%ted.europa.eu%%'
              AND LOWER(nd.file_type) = 'pdf'
        """)).scalar() or 0
        return {
            "ted_notices_total": total,
            "current_ted_documents": current_docs,
            "ted_pdf_documents": ted_pdf_docs,
            "dry_run": True,
            "message": f"{total} TED notices to re-extract. Set dry_run=false to run.",
        }

    # For large runs, use background task
    if limit > 2000 and background_tasks:
        def _run_backfill():
            from app.core.database import SessionLocal
            bg_db = SessionLocal()
            try:
                backfill_documents_for_all(
                    bg_db, source="TED_EU", replace=replace,
                    batch_size=10, limit=limit,
                )
            finally:
                bg_db.close()

        background_tasks.add_task(_run_backfill)
        return {
            "status": "background",
            "limit": limit,
            "replace": replace,
            "message": f"Backfill launched in background for up to {limit} notices. Check /document-stats to monitor.",
        }

    # Synchronous for small runs
    result = backfill_documents_for_all(
        db, source="TED_EU", replace=replace, batch_size=10, limit=limit,
    )
    return {**result, "replace": replace}


@router.get(
    "/document-stats",
    tags=["admin"],
    summary="Document pipeline statistics",
)
def document_pipeline_stats(
    db: Session = Depends(get_db),
) -> dict:
    """Document pipeline stats: docs by source, download status, sample notices with text."""
    from sqlalchemy import text as sql_text

    stats = {}

    # By source + status
    rows = db.execute(sql_text("""
        SELECT
            n.source,
            COUNT(DISTINCT nd.id) as total_docs,
            COUNT(DISTINCT CASE WHEN nd.extracted_text IS NOT NULL
                AND LENGTH(nd.extracted_text) > 50 THEN nd.id END) as with_text,
            COUNT(DISTINCT CASE WHEN nd.download_status = 'ok' THEN nd.id END) as downloaded,
            COUNT(DISTINCT CASE WHEN nd.download_status = 'failed' THEN nd.id END) as failed,
            COUNT(DISTINCT CASE WHEN nd.download_status = 'skipped' THEN nd.id END) as skipped
        FROM notice_documents nd
        JOIN notices n ON n.id = nd.notice_id
        GROUP BY n.source
    """)).fetchall()
    stats["by_source"] = [
        {"source": r[0], "total_docs": r[1], "with_text": r[2],
         "downloaded": r[3], "failed": r[4], "skipped": r[5]}
        for r in rows
    ]

    # By file_type
    rows2 = db.execute(sql_text("""
        SELECT COALESCE(nd.file_type, '(null)') as ft, COUNT(*) as cnt
        FROM notice_documents nd
        GROUP BY nd.file_type
        ORDER BY cnt DESC
        LIMIT 15
    """)).fetchall()
    stats["by_file_type"] = [{"file_type": r[0], "count": r[1]} for r in rows2]

    # By URL domain (top 10)
    rows3 = db.execute(sql_text("""
        SELECT
            CASE
                WHEN nd.url LIKE '%%ted.europa.eu%%' THEN 'ted.europa.eu'
                WHEN nd.url LIKE '%%publicprocurement.be%%' THEN 'publicprocurement.be'
                WHEN nd.url LIKE '%%cloud.3p.eu%%' THEN 'cloud.3p.eu'
                WHEN nd.url LIKE '%%upload://%%' THEN 'user-upload'
                ELSE 'other'
            END as domain,
            COUNT(*) as cnt
        FROM notice_documents nd
        GROUP BY domain
        ORDER BY cnt DESC
    """)).fetchall()
    stats["by_domain"] = [{"domain": r[0], "count": r[1]} for r in rows3]

    # Sample notices with extracted text (for Q&A testing)
    samples = db.execute(sql_text("""
        SELECT n.id, LEFT(n.title, 80) as title, n.source,
               COUNT(nd.id) as doc_count,
               SUM(CASE WHEN nd.extracted_text IS NOT NULL
                   AND LENGTH(nd.extracted_text) > 50 THEN 1 ELSE 0 END) as docs_with_text,
               MAX(LENGTH(nd.extracted_text)) as max_text_len
        FROM notices n
        JOIN notice_documents nd ON nd.notice_id = n.id
        WHERE nd.extracted_text IS NOT NULL AND LENGTH(nd.extracted_text) > 50
        GROUP BY n.id, n.title, n.source
        ORDER BY docs_with_text DESC, max_text_len DESC
        LIMIT 10
    """)).fetchall()
    stats["sample_notices_with_text"] = [
        {"notice_id": r[0], "title": r[1], "source": r[2],
         "doc_count": r[3], "docs_with_text": r[4], "max_text_len": r[5]}
        for r in samples
    ]

    return stats


# ── Phase 2b: BOSA Document Crawler (API-based) ─────────────────


@router.post(
    "/crawl-portal-documents",
    tags=["admin"],
    summary="Crawl BOSA portal API to discover and download PDF documents",
    description=(
        "Uses the BOSA portal API to list documents for each publication workspace, "
        "then downloads PDFs and extracts text.\n\n"
        "Targets BOSA notices with a workspace ID but no downloaded PDFs.\n"
        "Use dry_run=true first to see count."
    ),
)
def crawl_portal_documents(
    limit: int = Query(50, ge=1, le=1000, description="Max notices to crawl"),
    source: str = Query("BOSA_EPROC", description="Notice source"),
    download: bool = Query(True, description="Download PDFs (false = list only)"),
    dry_run: bool = Query(True, description="Preview only"),
    db: Session = Depends(get_db),
) -> dict:
    """Crawl BOSA portal API to discover and download procurement PDFs."""
    from app.services.document_crawler import batch_crawl_notices
    return batch_crawl_notices(
        db, limit=limit, source=source, download_pdfs=download, dry_run=dry_run,
    )


@router.post(
    "/crawl-notice/{notice_id}",
    tags=["admin"],
    summary="Crawl BOSA portal for a single notice",
)
def crawl_single_notice(
    notice_id: str,
    download: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Crawl BOSA portal API for a specific notice to discover PDF documents."""
    from app.services.document_crawler import crawl_bosa_documents
    from app.models.notice import ProcurementNotice

    notice = db.query(ProcurementNotice).filter(
        ProcurementNotice.id == notice_id
    ).first()
    if not notice:
        return {"status": "error", "message": "Notice not found"}

    workspace_id = notice.publication_workspace_id
    if not workspace_id:
        workspace_id = notice.source_id

    if not workspace_id:
        return {"status": "no_workspace_id", "notice_id": notice_id}

    results = crawl_bosa_documents(
        db, notice_id, workspace_id, download_pdfs=download,
    )
    return {
        "notice_id": notice_id,
        "workspace_id": workspace_id,
        "documents": results,
    }


# ── Phase 2b: BOSA API Document Explorer ─────────────────────────

# ── Phase 2b: BOSA Diagnostic ────────────────────────────────────


@router.post(
    "/bosa-explore-docs/{notice_id}",
    tags=["admin"],
    summary="Explore BOSA API to find documents for a notice",
)
def bosa_explore_docs(
    notice_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Minimal diagnostic: dump workspace detail and try /documents endpoint."""
    from app.connectors.bosa.client import _get_client
    from app.connectors.bosa.official_client import OfficialEProcurementClient
    from app.models.notice import ProcurementNotice
    import re
    import requests as req
    import traceback

    notice = db.query(ProcurementNotice).filter(
        ProcurementNotice.id == notice_id
    ).first()
    if not notice:
        return {"error": "Notice not found"}

    result = {
        "notice_id": notice_id,
        "source_id": notice.source_id,
        "publication_workspace_id": notice.publication_workspace_id,
    }

    # Get official BOSA client
    try:
        client, provider = _get_client()
        assert isinstance(client, OfficialEProcurementClient)
    except Exception as e:
        return {**result, "error": f"Client: {e}"}

    dos_base = client.dos_base_url.rstrip("/")
    ws_id = notice.publication_workspace_id or notice.source_id

    # ── TEST 1: Workspace detail via official client ──
    try:
        ws_data = client.get_publication_workspace(ws_id)
        if ws_data:
            # Check for XML in versions
            xml_ids = []
            has_xml = False
            for v in ws_data.get("versions", []):
                notice_obj = v.get("notice", {})
                xml = notice_obj.get("xmlContent", "")
                if xml:
                    has_xml = True
                    matches = re.findall(
                        r"publication-workspaces/([0-9a-f-]{36})", xml, re.IGNORECASE,
                    )
                    xml_ids.extend(matches)

            result["test1_workspace"] = {
                "status": "ok",
                "ws_id_returned": ws_data.get("id"),
                "version_count": len(ws_data.get("versions", [])),
                "has_xml_content": has_xml,
                "xml_workspace_ids": list(set(xml_ids)),
                "dossier_id": ws_data.get("dossierId"),
                "dossier_ref": ws_data.get("dossierReferenceNumber"),
                "notice_keys_in_version": list(
                    ws_data.get("versions", [{}])[0].get("notice", {}).keys()
                ) if ws_data.get("versions") else [],
            }
        else:
            result["test1_workspace"] = {"status": "not_found"}
    except Exception as e:
        result["test1_workspace"] = {"error": str(e), "tb": traceback.format_exc()[-500:]}

    # ── TEST 2: /documents via official client.request() (has BelGov-Trace-Id) ──
    try:
        url2 = f"{dos_base}/publication-workspaces/{ws_id}/documents?full=false&type=WORKSPACE"
        resp2 = client.request("GET", url2)
        result["test2_official_docs"] = {
            "url": url2,
            "status_code": resp2.status_code,
            "body": resp2.text[:500],
        }
    except Exception as e:
        result["test2_official_docs"] = {"error": str(e), "tb": traceback.format_exc()[-500:]}

    # ── TEST 3: /documents via portal API (publicprocurement.be) ──
    try:
        # Try portal API with BelGov-Trace-Id header
        import uuid as _uuid
        url3 = f"https://www.publicprocurement.be/api/dos/publication-workspaces/{ws_id}/documents?full=false&type=WORKSPACE&type=ESPD_REQUEST&type=SDI"
        portal_headers = {
            "Accept": "application/json",
            "BelGov-Trace-Id": str(_uuid.uuid4()),
            "Accept-Language": "fr",
        }
        resp3 = req.get(url3, headers=portal_headers, timeout=15)
        result["test3_portal_docs"] = {
            "url": url3,
            "status_code": resp3.status_code,
            "body": resp3.text[:500],
        }
    except Exception as e:
        result["test3_portal_docs"] = {"error": str(e), "tb": traceback.format_exc()[-500:]}

    # ── TEST 4: If XML found a different workspace ID, try that one ──
    xml_ids_found = result.get("test1_workspace", {}).get("xml_workspace_ids", [])
    for xid in xml_ids_found:
        if xid != ws_id:
            try:
                url4 = f"{dos_base}/publication-workspaces/{xid}/documents?full=false&type=WORKSPACE"
                resp4 = client.request("GET", url4)
                test4 = {
                    "xml_workspace_id": xid,
                    "status_code": resp4.status_code,
                }
                if resp4.status_code == 200:
                    data4 = resp4.json()
                    if isinstance(data4, list):
                        test4["doc_count"] = len(data4)
                        test4["sample"] = [
                            d.get("titles", [{}])[0].get("text", "?")
                            for d in data4[:3]
                        ]
                else:
                    test4["body"] = resp4.text[:300]
                result[f"test4_xml_id_{xid[:8]}"] = test4
            except Exception as e:
                result[f"test4_xml_id_{xid[:8]}"] = {"error": str(e)}

    return result
