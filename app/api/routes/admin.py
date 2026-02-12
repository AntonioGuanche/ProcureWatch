"""Admin endpoints: manual import trigger + import runs monitoring."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_admin_key, rate_limit_admin
from app.db.session import get_db
from app.services.notice_service import NoticeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_key), Depends(rate_limit_admin)],
)


# ── Manual import trigger ────────────────────────────────────────────


@router.post("/import")
async def trigger_import(
    sources: str = Query("BOSA,TED", description="Comma-separated: BOSA,TED"),
    term: str = Query("*", description="Search term"),
    page_size: int = Query(25, ge=1, le=250, description="Results per page"),
    max_pages: int = Query(1, ge=1, le=100, description="Max pages to fetch"),
    fetch_details: bool = Query(False, description="Fetch full workspace details (BOSA)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger a manual import. Useful for testing and one-off data refreshes.
    Returns per-source stats and saves to import_runs table.
    """
    source_list = [s.strip().upper() for s in sources.split(",") if s.strip()]
    if not source_list:
        source_list = ["BOSA", "TED"]

    svc = NoticeService(db)
    results: dict[str, Any] = {}
    started_at = datetime.now(timezone.utc)

    for source in source_list:
        if source not in ("BOSA", "TED"):
            results[source.lower()] = {"error": f"Unknown source: {source}"}
            continue

        source_stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
        run_start = datetime.now(timezone.utc)

        for page in range(1, max_pages + 1):
            try:
                items = _fetch_page(source, term, page, page_size)
                if not items:
                    break

                if source == "BOSA":
                    stats = await asyncio.to_thread(
                        lambda: asyncio.run(
                            svc.import_from_eproc_search(items, fetch_details=fetch_details)
                        )
                    )
                else:
                    stats = await asyncio.to_thread(
                        lambda: asyncio.run(
                            svc.import_from_ted_search(items, fetch_details=fetch_details)
                        )
                    )

                source_stats["created"] += stats["created"]
                source_stats["updated"] += stats["updated"]
                source_stats["skipped"] += stats.get("skipped", 0)
                source_stats["errors"].extend(stats.get("errors", []))
            except Exception as e:
                source_stats["errors"].append({"page": page, "message": str(e)})
                logger.exception("[%s] Import page %s failed", source, page)

        run_end = datetime.now(timezone.utc)
        results[source.lower()] = source_stats

        # Save to import_runs
        try:
            _save_import_run(
                db, source, run_start, run_end,
                source_stats["created"], source_stats["updated"],
                len(source_stats["errors"]),
                source_stats["errors"] or None,
                {"term": term, "page_size": page_size, "max_pages": max_pages, "trigger": "api"},
            )
        except Exception as e:
            logger.warning("Failed to save import_run: %s", e)

    total_created = sum(r.get("created", 0) for r in results.values() if isinstance(r, dict))
    total_updated = sum(r.get("updated", 0) for r in results.values() if isinstance(r, dict))
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    # Run watchlist matcher if new notices were imported
    matcher_summary = None
    if total_created > 0:
        try:
            from app.services.watchlist_matcher import run_watchlist_matcher
            matcher_summary = run_watchlist_matcher(db)
            logger.info(
                "Watchlist matcher: %d watchlists, %d new matches, %d emails",
                matcher_summary.get("watchlists_processed", 0),
                matcher_summary.get("total_new_matches", 0),
                matcher_summary.get("emails_sent", 0),
            )
        except Exception as e:
            logger.warning("Watchlist matcher failed: %s", e)
            matcher_summary = {"error": str(e)}

    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "total": {"created": total_created, "updated": total_updated},
        "watchlist_matcher": matcher_summary,
        **results,
    }


def _fetch_page(source: str, term: str, page: int, page_size: int) -> list[dict]:
    """Fetch one page of results from BOSA or TED."""
    if source == "BOSA":
        from app.connectors.bosa.client import search_publications
        result = search_publications(term=term, page=page, page_size=page_size)
        payload = result.get("json") or {}
        if isinstance(payload, dict):
            for key in ("publications", "items", "results", "data"):
                candidate = payload.get(key)
                if isinstance(candidate, list):
                    return candidate
        return []
    else:
        from app.connectors.ted.client import search_ted_notices
        result = search_ted_notices(term=term, page=page, page_size=page_size)
        return result.get("notices") or (result.get("json") or {}).get("notices") or []


def _save_import_run(
    db: Session,
    source: str,
    started_at: datetime,
    completed_at: datetime,
    created_count: int,
    updated_count: int,
    error_count: int,
    errors_json: Optional[list],
    search_criteria_json: dict,
) -> None:
    """Insert one row into import_runs."""
    db.execute(
        text("""
            INSERT INTO import_runs
            (id, source, started_at, completed_at, created_count, updated_count, error_count, errors_json, search_criteria_json)
            VALUES (:id, :source, :started_at, :completed_at, :created_count, :updated_count, :error_count, :errors_json, :search_criteria_json)
        """),
        {
            "id": str(uuid4()),
            "source": source,
            "started_at": started_at,
            "completed_at": completed_at,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors_json": json.dumps(errors_json, default=str) if errors_json else None,
            "search_criteria_json": json.dumps(search_criteria_json, default=str),
        },
    )
    db.commit()


# ── Import runs monitoring ───────────────────────────────────────────


@router.get("/import-runs")
async def list_import_runs(
    limit: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None, description="Filter by source: BOSA or TED"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent import runs with stats."""
    query = "SELECT * FROM import_runs"
    params: dict[str, Any] = {}

    if source:
        query += " WHERE source = :source"
        params["source"] = source.upper()

    query += " ORDER BY started_at DESC LIMIT :limit"
    params["limit"] = limit

    rows = db.execute(text(query), params).mappings().all()

    runs = []
    for row in rows:
        run = dict(row)
        # Parse JSON fields
        for json_field in ("errors_json", "search_criteria_json"):
            if run.get(json_field) and isinstance(run[json_field], str):
                try:
                    run[json_field] = json.loads(run[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        runs.append(run)

    return {"count": len(runs), "runs": runs}


@router.get("/import-runs/summary")
async def import_runs_summary(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Quick summary: last run per source + totals."""
    rows = db.execute(text("""
        SELECT source,
               MAX(started_at) as last_run,
               SUM(created_count) as total_created,
               SUM(updated_count) as total_updated,
               SUM(error_count) as total_errors,
               COUNT(*) as run_count
        FROM import_runs
        GROUP BY source
    """)).mappings().all()

    summary = {}
    for row in rows:
        summary[row["source"]] = {
            "last_run": str(row["last_run"]) if row["last_run"] else None,
            "total_created": row["total_created"] or 0,
            "total_updated": row["total_updated"] or 0,
            "total_errors": row["total_errors"] or 0,
            "run_count": row["run_count"] or 0,
        }

    # Total notices in DB
    total = db.execute(text("SELECT COUNT(*) as cnt FROM notices")).scalar()

    return {"sources": summary, "total_notices": total or 0}


@router.post("/bulk-import", tags=["admin"])
def trigger_bulk_import(
    sources: str = Query("BOSA,TED", description="Comma-separated: BOSA,TED"),
    term: str = Query("*", description="Search term"),
    term_ted: Optional[str] = Query(None, description="TED expert query override (e.g. 'notice-type = can' for award notices)"),
    ted_days_back: int = Query(3, ge=1, le=3650, description="TED rolling date window in days (default: 3, use 3650 for full history)"),
    page_size: int = Query(100, ge=1, le=250, description="Results per page"),
    max_pages: Optional[int] = Query(None, ge=0, le=100, description="Max pages (None=auto, 0=skip fetch/backfill only)"),
    fetch_details: bool = Query(False, description="Fetch workspace details (BOSA, slower)"),
    run_backfill: bool = Query(True, description="Run enrichment backfill after import"),
    run_matcher: bool = Query(True, description="Run watchlist matcher after import"),
    date_from: Optional[str] = Query(None, description="BOSA publication date from (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="BOSA publication date to (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Bulk import: auto-paginates through all available results.
    Much larger than /import (which fetches 1 page by default).
    Returns per-page breakdown and triggers backfill + matcher.

    TED CAN import example:
        term_ted=notice-type = can&ted_days_back=365&sources=TED
    """
    from app.services.bulk_import import bulk_import_all
    return bulk_import_all(
        db, sources=sources, term=term, term_ted=term_ted,
        ted_days_back=ted_days_back, page_size=page_size,
        max_pages=max_pages, fetch_details=fetch_details,
        run_backfill=run_backfill, run_matcher=run_matcher,
        date_from=date_from, date_to=date_to,
    )


@router.post("/match-watchlists", tags=["admin"])
def trigger_watchlist_matcher(
    db: Session = Depends(get_db),
) -> dict:
    """
    Manually trigger watchlist matcher for all enabled watchlists.
    Useful for testing or after bulk imports.
    """
    from app.services.watchlist_matcher import run_watchlist_matcher
    return run_watchlist_matcher(db)


@router.get("/data-quality", tags=["admin"])
def data_quality_report(
    db: Session = Depends(get_db),
) -> dict:
    """
    Data quality report: fill rate per field, per source.
    Shows which fields need enrichment.
    """
    from app.services.enrichment_service import get_data_quality_report
    return get_data_quality_report(db)


@router.post("/backfill", tags=["admin"])
def trigger_backfill(
    source: Optional[str] = Query(None, description="Filter: BOSA_EPROC or TED_EU"),
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Max notices to process"),
    refresh_vectors: bool = Query(True, description="Refresh search_vector after backfill"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Backfill missing fields from existing raw_data (no external API calls).
    Re-extracts: description, organisation_names, notice_type, url, nuts_codes, etc.
    Optionally refreshes search_vector for full-text search.
    """
    from app.services.enrichment_service import backfill_from_raw_data, refresh_search_vectors

    result = backfill_from_raw_data(db, source=source, limit=limit)

    if refresh_vectors and result.get("enriched", 0) > 0:
        try:
            rows = refresh_search_vectors(db)
            result["search_vectors_refreshed"] = rows
        except Exception as e:
            result["search_vectors_error"] = str(e)
            logger.warning("search_vector refresh failed: %s", e)

    return result


@router.get("/scheduler", tags=["admin"])
def scheduler_status() -> dict:
    """
    Scheduler status: enabled, running, config, jobs, last run result.
    """
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()


@router.post("/scheduler/run-now", tags=["admin"])
def scheduler_run_now(
    db: Session = Depends(get_db),
) -> dict:
    """
    Manually trigger the scheduled import pipeline (same as what the cron runs).
    Runs synchronously and returns the result.
    """
    from app.services.scheduler import _run_import_pipeline, _last_run
    _run_import_pipeline()
    return _last_run.get("import_pipeline", {"status": "no result"})


@router.get("/raw-data-keys", tags=["admin"])
def raw_data_keys_report(
    source: Optional[str] = Query(None, description="BOSA_EPROC or TED_EU"),
    sample: int = Query(5, ge=1, le=20, description="Number of notices to sample"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Diagnostic: show top-level keys and sample values from raw_data.
    Helps understand what fields are available for enrichment.
    """
    from app.models.notice import ProcurementNotice as Notice
    query = db.query(Notice).filter(Notice.raw_data.isnot(None))
    if source:
        query = query.filter(Notice.source == source)
    notices = query.limit(sample).all()

    key_freq: dict[str, int] = {}
    samples: list[dict] = []
    for n in notices:
        raw = n.raw_data
        if not isinstance(raw, dict):
            continue
        for k in raw.keys():
            key_freq[k] = key_freq.get(k, 0) + 1
        # Sample: show first 200 chars of each value
        sample_entry = {"source_id": n.source_id, "source": n.source, "keys": list(raw.keys())}
        for field in ("description", "noticeType", "notice_type", "notice-type",
                       "formType", "form_type", "form-type", "summary",
                       "type", "dossier", "organisation"):
            val = raw.get(field)
            if val is not None:
                sample_entry[f"raw.{field}"] = str(val)[:200]
        samples.append(sample_entry)

    sorted_keys = sorted(key_freq.items(), key=lambda x: -x[1])
    return {
        "sampled": len(notices),
        "top_keys": dict(sorted_keys[:30]),
        "samples": samples,
    }


# ── Duplicate cleanup ────────────────────────────────────────────────

@router.get("/cleanup/duplicates", summary="Check for duplicate notices (dry run)")
def check_duplicates(
    db: Session = Depends(get_db),
):
    """Find duplicate BOSA notices (same dossier_id). Returns stats only."""
    from app.services.cleanup_service import cleanup_bosa_duplicates
    return cleanup_bosa_duplicates(db, dry_run=True)


@router.post("/cleanup/duplicates", summary="Remove duplicate notices")
def remove_duplicates(
    db: Session = Depends(get_db),
):
    """Delete duplicate BOSA notices, keeping the newest publication per dossier."""
    from app.services.cleanup_service import cleanup_bosa_duplicates
    return cleanup_bosa_duplicates(db, dry_run=False)


# ── Test email ────────────────────────────────────────────────────────


@router.post("/test-email", tags=["admin"])
def test_email(
    to: str = Query(..., description="Recipient email address"),
) -> dict:
    """Send a test HTML email to verify email configuration."""
    from app.notifications.emailer import send_email_html

    subject = "ProcureWatch – Test Email"
    html_body = (
        "<h2>ProcureWatch Test Email</h2>"
        "<p>If you can read this, your email configuration is working correctly.</p>"
        f"<p><small>Sent at {datetime.now(timezone.utc).isoformat()}</small></p>"
    )

    try:
        send_email_html(to=to, subject=subject, html_body=html_body)
        return {"status": "ok", "to": to, "mode": _get_email_mode()}
    except Exception as e:
        logger.exception("Test email failed to=%s", to)
        return {"status": "error", "to": to, "mode": _get_email_mode(), "error": str(e)}


def _get_email_mode() -> str:
    """Return current email mode for diagnostics."""
    from app.core.config import settings as _s
    raw = getattr(_s, "email_mode", None) or "file"
    return str(raw).split("#")[0].strip().lower() or "file"


# ── Merge CAN → CN ────────────────────────────────────────────────────

@router.post("/merge-cans", tags=["admin"])
def merge_cans(
    limit: int = Query(5000, ge=1, le=50000, description="Max CAN records to process"),
    dry_run: bool = Query(False, description="Preview without committing"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Merge orphan CAN (form_type='result') records into matching CN notices
    via procedure_id. Transfers award fields and deletes the CAN.
    Run multiple times if total_scanned == limit (more to process).
    """
    from app.services.enrichment_service import merge_orphan_cans
    return merge_orphan_cans(db, limit=limit, dry_run=dry_run)


@router.post("/cleanup-orphan-cans", tags=["admin"])
def cleanup_orphan_cans(
    limit: int = Query(50000, ge=1, le=100000, description="Max CAN records to scan"),
    dry_run: bool = Query(True, description="Preview without deleting"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Delete orphan CAN records (form_type='result') that have no matching CN.
    Preserves CANs with useful standalone award data (winner + value).
    Run with dry_run=true first to preview.
    """
    from app.services.enrichment_service import cleanup_orphan_cans
    return cleanup_orphan_cans(db, limit=limit, dry_run=dry_run)


# ── BOSA diagnostics & backfill ──────────────────────────────────────

@router.get("/bosa-diagnostics", tags=["admin"])
def bosa_diagnostics(db: Session = Depends(get_db)) -> dict:
    """
    Diagnostic: distribution of form_type, notice_sub_type, URL coverage,
    procedure_id coverage for BOSA notices.
    """
    from app.models.notice import ProcurementNotice as Notice
    from sqlalchemy import func

    base = db.query(func.count(Notice.id)).filter(Notice.source == "BOSA_EPROC")
    total = base.scalar()

    # form_type distribution
    form_types = (
        db.query(Notice.form_type, func.count(Notice.id))
        .filter(Notice.source == "BOSA_EPROC")
        .group_by(Notice.form_type)
        .order_by(func.count(Notice.id).desc())
        .all()
    )

    # notice_sub_type distribution
    sub_types = (
        db.query(Notice.notice_sub_type, func.count(Notice.id))
        .filter(Notice.source == "BOSA_EPROC")
        .group_by(Notice.notice_sub_type)
        .order_by(func.count(Notice.id).desc())
        .all()
    )

    # URL coverage
    has_url = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.url.isnot(None), Notice.url != ""
    ).scalar()

    # procedure_id coverage
    has_proc_id = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.procedure_id.isnot(None), Notice.procedure_id != ""
    ).scalar()

    # award fields coverage
    has_winner = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.award_winner_name.isnot(None)
    ).scalar()
    has_award_val = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.award_value.isnot(None)
    ).scalar()

    return {
        "total": total,
        "form_types": {str(k): v for k, v in form_types},
        "notice_sub_types": {str(k): v for k, v in sub_types},
        "url_coverage": {"filled": has_url, "pct": round(has_url / total * 100, 1) if total else 0},
        "procedure_id_coverage": {"filled": has_proc_id, "pct": round(has_proc_id / total * 100, 1) if total else 0},
        "award_winner_name": {"filled": has_winner, "pct": round(has_winner / total * 100, 1) if total else 0},
        "award_value": {"filled": has_award_val, "pct": round(has_award_val / total * 100, 1) if total else 0},
    }


@router.post("/bosa-backfill-urls", tags=["admin"])
def bosa_backfill_urls(
    limit: int = Query(50000, ge=1, le=200000),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Backfill URLs for BOSA notices using source_id (= publicationWorkspaceId).
    URL pattern: https://publicprocurement.be/publication-workspaces/{source_id}/general
    """
    from app.models.notice import ProcurementNotice as Notice
    from sqlalchemy import or_

    notices = (
        db.query(Notice)
        .filter(
            Notice.source == "BOSA_EPROC",
            or_(Notice.url.is_(None), Notice.url == ""),
            Notice.source_id.isnot(None),
            Notice.source_id != "",
        )
        .limit(limit)
        .all()
    )

    updated = 0
    for n in notices:
        url = f"https://publicprocurement.be/publication-workspaces/{n.source_id}/general"
        if not dry_run:
            n.url = url
        updated += 1

    if not dry_run and updated:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return {"error": str(e), "updated": 0}

    return {"updated": updated, "total_missing": len(notices), "dry_run": dry_run}


# ── BOSA deep sample: explore what's really inside type 29 (CAN) ──────


@router.get("/bosa-sample-can", tags=["admin"])
def bosa_sample_can(
    limit: int = Query(3, ge=1, le=10),
    notice_sub_type: str = Query("29"),
    fetch_workspace: bool = Query(True),
    fetch_notice: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Sample BOSA notices of a given noticeSubType and explore their content:
    1. raw_data from DB (search result)
    2. /publication-workspaces/{id} detail (Dos API)
    3. /notices/{notice-id} detail (Dos API) for each noticeId
    """
    from app.models.notice import ProcurementNotice as Notice

    # Get sample notices
    notices = (
        db.query(Notice)
        .filter(
            Notice.source == "BOSA_EPROC",
            Notice.notice_sub_type == notice_sub_type,
        )
        .order_by(Notice.published_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    if not notices:
        return {"error": f"No BOSA notices with notice_sub_type={notice_sub_type}"}

    # Try to get BOSA client for detail APIs
    workspace_client = None
    if fetch_workspace or fetch_notice:
        try:
            from app.connectors.bosa.client import _get_client
            from app.connectors.bosa.official_client import OfficialEProcurementClient
            client, provider = _get_client()
            if isinstance(client, OfficialEProcurementClient):
                workspace_client = client
            else:
                logger.warning("BOSA client is not official, can't fetch detail: %s", provider)
        except Exception as e:
            logger.warning("Failed to get BOSA client: %s", e)

    results = []
    for n in notices:
        item: dict[str, Any] = {
            "db_id": n.id,
            "source_id": n.source_id,
            "title": n.title[:120] if n.title else None,
            "notice_sub_type": n.notice_sub_type,
            "form_type": n.form_type,
            "procedure_id": n.procedure_id,
            "published_at": str(n.published_at) if n.published_at else None,
            "award_winner_name": n.award_winner_name,
            "award_value": str(n.award_value) if n.award_value else None,
        }

        # 1. Raw data from DB (keys summary + full dump)
        raw = n.raw_data or {}
        item["raw_data_keys"] = sorted(raw.keys())
        item["raw_data_full"] = raw

        # Extract noticeIds from raw_data
        notice_ids = raw.get("noticeIds") or []
        item["notice_ids_in_raw"] = notice_ids

        # 2. Fetch workspace detail
        if fetch_workspace and workspace_client and n.source_id:
            try:
                ws = workspace_client.get_publication_workspace(n.source_id)
                if ws:
                    item["workspace_detail_keys"] = sorted(ws.keys()) if isinstance(ws, dict) else str(type(ws))
                    item["workspace_detail"] = ws
                else:
                    item["workspace_detail"] = None
                    item["workspace_detail_error"] = "returned None (404/401/403?)"
            except Exception as e:
                item["workspace_detail_error"] = str(e)

        # 3. Fetch notice detail for each noticeId
        if fetch_notice and workspace_client and notice_ids:
            item["notice_details"] = []
            for nid in notice_ids[:3]:  # max 3 per notice
                try:
                    nd = workspace_client.get_notice(nid)
                    if nd:
                        item["notice_details"].append({
                            "notice_id": nid,
                            "keys": sorted(nd.keys()) if isinstance(nd, dict) else str(type(nd)),
                            "detail": nd,
                        })
                    else:
                        item["notice_details"].append({
                            "notice_id": nid,
                            "error": "returned None (404/401/403?)",
                        })
                except Exception as e:
                    item["notice_details"].append({
                        "notice_id": nid,
                        "error": str(e),
                    })

        results.append(item)

    return {
        "notice_sub_type": notice_sub_type,
        "sample_count": len(results),
        "client_available": workspace_client is not None,
        "samples": results,
    }
