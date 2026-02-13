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


@router.post("/rescore-all-matches", tags=["admin"])
def rescore_all_matches(
    watchlist_id: Optional[str] = Query(None, description="Single watchlist ID (omit = all)"),
    dry_run: bool = Query(True, description="Preview only — set false to execute"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Recalculate relevance_score for all existing watchlist matches.
    Does NOT delete/recreate matches — only updates the score column.
    Use after deploying scoring changes or company profile updates.
    """
    from app.models.watchlist_match import WatchlistMatch
    from app.models.watchlist import Watchlist
    from app.models.notice import ProcurementNotice as Notice
    from app.models.user import User
    from app.services.relevance_scoring import calculate_relevance_score

    # Build match query
    match_query = db.query(WatchlistMatch)
    if watchlist_id:
        match_query = match_query.filter(WatchlistMatch.watchlist_id == watchlist_id)

    total_matches = match_query.count()

    if dry_run:
        null_scores = match_query.filter(WatchlistMatch.relevance_score.is_(None)).count()
        return {
            "total_matches": total_matches,
            "null_scores": null_scores,
            "dry_run": True,
            "message": "Set dry_run=false to recalculate all scores",
        }

    # Preload watchlists + users
    wl_ids = [r[0] for r in match_query.with_entities(WatchlistMatch.watchlist_id).distinct().all()]
    watchlists = {wl.id: wl for wl in db.query(Watchlist).filter(Watchlist.id.in_(wl_ids)).all()}
    user_ids = {wl.user_id for wl in watchlists.values() if wl.user_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    # Process in batches
    BATCH = 500
    updated = 0
    errors = 0
    offset = 0

    while offset < total_matches:
        matches = (
            match_query
            .order_by(WatchlistMatch.id)
            .offset(offset)
            .limit(BATCH)
            .all()
        )
        if not matches:
            break

        # Batch-load notices
        notice_ids = [m.notice_id for m in matches]
        notice_map = {n.id: n for n in db.query(Notice).filter(Notice.id.in_(notice_ids)).all()}

        for match in matches:
            try:
                wl = watchlists.get(match.watchlist_id)
                notice = notice_map.get(match.notice_id)
                if not wl or not notice:
                    continue

                user = users.get(wl.user_id) if wl.user_id else None
                score, explanation = calculate_relevance_score(notice, wl, user=user)

                match.relevance_score = score
                match.matched_on = explanation
                updated += 1
            except Exception as e:
                logger.warning("Rescore error match %s: %s", match.id, e)
                errors += 1

        db.commit()
        offset += BATCH
        logger.info("Rescore progress: %d/%d updated, %d errors", updated, total_matches, errors)

    return {
        "total_matches": total_matches,
        "updated": updated,
        "errors": errors,
        "dry_run": False,
    }


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
    limit: int = Query(200000, ge=1, le=500000),
    dry_run: bool = Query(True),
    batch_size: int = Query(5000, ge=100, le=10000),
    db: Session = Depends(get_db),
) -> dict:
    """
    Backfill URLs for BOSA notices using raw SQL batched updates.
    URL pattern: https://publicprocurement.be/publication-workspaces/{source_id}/general
    Each batch = single UPDATE ... WHERE id IN (SELECT ... LIMIT N) → no ORM overhead.
    """
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "AND (url IS NULL OR url = '') "
        "AND source_id IS NOT NULL AND source_id != ''"
    ))
    total_missing = count_result.scalar()

    if dry_run:
        return {"updated": min(total_missing, limit), "total_missing": total_missing, "dry_run": True}

    updated = 0
    batches = 0
    errors = []

    while updated < limit:
        try:
            result = db.execute(text(
                "UPDATE notices SET "
                "  url = 'https://publicprocurement.be/publication-workspaces/' "
                "        || source_id || '/general', "
                "  updated_at = now() "
                "WHERE id IN ("
                "  SELECT id FROM notices "
                "  WHERE source = 'BOSA_EPROC' "
                "  AND (url IS NULL OR url = '') "
                "  AND source_id IS NOT NULL AND source_id != '' "
                "  LIMIT :batch_size"
                ")"
            ), {"batch_size": batch_size})
            db.commit()
            rows = result.rowcount
            if rows == 0:
                break
            updated += rows
            batches += 1
            logger.info("bosa-backfill-urls: batch %d → %d rows (total %d)",
                        batches, rows, updated)
        except Exception as e:
            db.rollback()
            errors.append(f"batch {batches}: {str(e)[:200]}")
            logger.error("bosa-backfill-urls error at batch %d: %s", batches, e)
            break

    return {
        "updated": updated,
        "total_missing": total_missing,
        "batches": batches,
        "batch_size": batch_size,
        "errors": errors if errors else None,
        "dry_run": False,
    }


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
        .order_by(Notice.publication_date.desc().nulls_last())
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
            "publication_date": str(n.publication_date) if n.publication_date else None,
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


# ── BOSA CAN award parsing (eForms XML) ─────────────────────────────


@router.get("/bosa-parse-awards-test")
def bosa_parse_awards_test(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Test the eForms XML parser on a few BOSA CAN notices.
    Returns parsed award data WITHOUT updating the DB.
    """
    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Find BOSA CANs (type 29) that have raw_data with versions
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        item: dict[str, Any] = {
            "id": str(row[0]),
            "source_id": row[1],
            "title": row[2],
        }
        raw_data = row[3]
        if not isinstance(raw_data, dict):
            try:
                raw_data = json.loads(raw_data) if raw_data else {}
            except (json.JSONDecodeError, TypeError):
                raw_data = {}

        xml_content = extract_xml_from_raw_data(raw_data)
        if not xml_content:
            item["status"] = "no_xml_found"
            item["versions_count"] = len(raw_data.get("versions", []))
            results.append(item)
            continue

        item["xml_length"] = len(xml_content)
        parsed = parse_award_data(xml_content)
        fields = build_notice_fields(parsed)

        # Convert Decimals to str for JSON serialization
        serializable_parsed = _serialize_parsed(parsed)

        item["status"] = "parsed"
        item["parsed"] = serializable_parsed
        item["db_fields"] = {
            k: str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "Decimal" else v
            for k, v in fields.items()
        }
        results.append(item)

    return {
        "test_count": len(results),
        "parsed_ok": sum(1 for r in results if r.get("status") == "parsed"),
        "no_xml": sum(1 for r in results if r.get("status") == "no_xml_found"),
        "results": results,
    }


@router.post("/bosa-enrich-awards")
def bosa_enrich_awards(
    limit: int = Query(50000, ge=1, le=200000),
    batch_size: int = Query(500, ge=10, le=2000),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Bulk-enrich BOSA CAN (type 29) notices with award data parsed from eForms XML.
    Updates: award_winner_name, award_value, award_date, number_tenders_received, award_criteria_json.
    """
    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Count eligible CANs (type 29 with raw_data, award fields empty)
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '')"
    ))
    total_eligible = count_result.scalar()

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "dry_run": True,
            "message": "Set dry_run=false to execute enrichment",
        }

    # Process in batches — we MUST load raw_data so we use ORM selectively
    enriched = 0
    skipped = 0
    errors = 0
    batches = 0
    offset = 0

    while enriched + skipped + errors < limit:
        rows = db.execute(text(
            "SELECT id, raw_data FROM notices "
            "WHERE source = 'BOSA_EPROC' "
            "  AND notice_sub_type = '29' "
            "  AND raw_data IS NOT NULL "
            "  AND (award_winner_name IS NULL OR award_winner_name = '') "
            "ORDER BY id "
            "LIMIT :batch_size OFFSET :offset"
        ), {"batch_size": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        batch_updates = []
        for row in rows:
            notice_id = row[0]
            raw_data = row[1]

            try:
                if not isinstance(raw_data, dict):
                    raw_data = json.loads(raw_data) if raw_data else {}

                xml_content = extract_xml_from_raw_data(raw_data)
                if not xml_content:
                    skipped += 1
                    continue

                parsed = parse_award_data(xml_content)
                fields = build_notice_fields(parsed)

                if not fields:
                    skipped += 1
                    continue

                batch_updates.append((notice_id, fields))

            except Exception as e:
                logger.warning("Award parse error for notice %s: %s", notice_id, e)
                errors += 1

        # Bulk UPDATE via individual statements per notice (fields vary)
        for notice_id, fields in batch_updates:
            set_clauses = []
            params: dict[str, Any] = {"nid": notice_id}

            if "award_winner_name" in fields:
                set_clauses.append("award_winner_name = :winner")
                params["winner"] = fields["award_winner_name"]
            if "award_value" in fields:
                set_clauses.append("award_value = :value")
                params["value"] = float(fields["award_value"])
            if "award_date" in fields:
                set_clauses.append("award_date = :adate")
                params["adate"] = str(fields["award_date"])
            if "number_tenders_received" in fields:
                set_clauses.append("number_tenders_received = :ntenders")
                params["ntenders"] = fields["number_tenders_received"]
            if "award_criteria_json" in fields:
                set_clauses.append("award_criteria_json = :acjson")
                # Serialize Decimals for JSON storage
                params["acjson"] = json.dumps(
                    fields["award_criteria_json"],
                    default=str,
                )

            if set_clauses:
                set_clauses.append("updated_at = now()")
                sql = f"UPDATE notices SET {', '.join(set_clauses)} WHERE id = :nid"
                db.execute(text(sql), params)
                enriched += 1

        db.commit()
        batches += 1
        offset += batch_size

        logger.info(
            "Award enrichment batch %d: enriched=%d, skipped=%d, errors=%d",
            batches, enriched, skipped, errors,
        )

    return {
        "total_eligible": total_eligible,
        "enriched": enriched,
        "skipped": skipped,
        "errors": errors,
        "batches": batches,
        "dry_run": False,
    }


def _serialize_parsed(parsed: dict) -> dict:
    """Convert Decimal/date values to JSON-safe types."""
    out = {}
    for k, v in parsed.items():
        if v is None:
            out[k] = None
        elif isinstance(v, list):
            out[k] = [
                {
                    kk: str(vv) if hasattr(vv, "__class__") and vv.__class__.__name__ in ("Decimal", "date") else vv
                    for kk, vv in item.items()
                }
                if isinstance(item, dict) else item
                for item in v
            ]
        elif hasattr(v, "__class__") and v.__class__.__name__ in ("Decimal", "date"):
            out[k] = str(v)
        else:
            out[k] = v
    return out


# ── TED CPV cleanup (fix ['xxxx'] format) ─────────────────────────────

@router.post(
    "/fix-ted-cpv",
    tags=["admin"],
    summary="Fix TED CPV codes stored as ['xxxx'] instead of clean codes",
    description=(
        "Strips brackets/quotes from cpv_main_code for TED notices.\n"
        "Also re-derives cpv_division (first 2 digits) for facet accuracy."
    ),
)
def fix_ted_cpv(
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Clean up TED CPV codes stored with list formatting."""
    import re

    # Find all notices with malformed CPV (contains [ or ')
    rows = db.execute(text(
        "SELECT id, cpv_main_code FROM notices "
        "WHERE cpv_main_code IS NOT NULL "
        "  AND (cpv_main_code LIKE '%[%' OR cpv_main_code LIKE '%]%' "
        "       OR cpv_main_code LIKE '%''%')"
    )).fetchall()

    if dry_run:
        samples = [{"id": str(r[0]), "before": r[1]} for r in rows[:20]]
        return {
            "total_malformed": len(rows),
            "dry_run": True,
            "samples": samples,
            "message": "Set dry_run=false to fix",
        }

    fixed = 0
    for row in rows:
        notice_id, raw_cpv = row[0], row[1]
        # Extract digits and dash from the messy string: "['44411000']" → "44411000"
        cleaned = re.sub(r"[\[\]\"' ]", "", raw_cpv).strip()
        # If multiple codes separated by comma, take the first
        if "," in cleaned:
            cleaned = cleaned.split(",")[0].strip()

        if cleaned and cleaned != raw_cpv:
            db.execute(text(
                "UPDATE notices SET cpv_main_code = :cpv WHERE id = :id"
            ), {"cpv": cleaned, "id": notice_id})
            fixed += 1

    db.commit()
    return {"total_malformed": len(rows), "fixed": fixed}


# ── TED CAN award enrichment (re-fetch expanded fields) ──────────────

@router.post(
    "/ted-can-enrich",
    tags=["admin"],
    summary="Re-enrich TED CANs that have country-code-only winner names",
    description=(
        "Finds TED notices where award_winner_name is just a country code (e.g. 'BEL', 'FR')\n"
        "and re-fetches from TED search with expanded fields (organisation-name-tenderer, etc.).\n"
        "Fixes the gap where DEFAULT_FIELDS didn't include winner detail fields."
    ),
)
def ted_can_enrich(
    limit: int = Query(500, ge=1, le=5000, description="Max notices to process"),
    batch_size: int = Query(10, ge=1, le=50, description="Notices per batch"),
    api_delay_ms: int = Query(500, ge=100, le=5000, description="Delay between API calls (ms)"),
    dry_run: bool = Query(True, description="Preview only — set false to execute"),
    db: Session = Depends(get_db),
) -> dict:
    """Re-enrich TED CANs with proper winner names."""
    from app.services.ted_award_enrichment import enrich_ted_can_batch
    return enrich_ted_can_batch(
        db,
        limit=limit,
        batch_size=batch_size,
        api_delay_ms=api_delay_ms,
        dry_run=dry_run,
    )


@router.get("/bosa-can-formats")
def bosa_can_formats(
    limit: int = Query(500, ge=10, le=5000),
    db: Session = Depends(get_db),
):
    """
    Diagnose raw_data formats across BOSA CAN (type 29) notices.
    Helps understand why most notices were skipped during award enrichment.
    """
    rows = db.execute(text(
        "SELECT id, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    formats: dict[str, int] = {}
    top_level_keys: dict[str, int] = {}
    samples: dict[str, list] = {}

    for row in rows:
        raw = row[1]
        if not isinstance(raw, dict):
            try:
                raw = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                raw = {}

        # Classify format
        has_versions = "versions" in raw and isinstance(raw.get("versions"), list) and len(raw.get("versions", [])) > 0
        has_xml = False
        if has_versions:
            for v in raw["versions"]:
                if isinstance(v, dict) and isinstance(v.get("notice"), dict):
                    xml = v["notice"].get("xmlContent", "")
                    if isinstance(xml, str) and xml.startswith("<?xml"):
                        has_xml = True
                        break

        has_flat_fields = any(
            k in raw for k in ["publicationType", "publicationWorkspaceId", "dossierStatus", "natures"]
        )

        if has_xml:
            fmt = "versions_with_xml"
        elif has_versions:
            fmt = "versions_no_xml"
        elif has_flat_fields:
            fmt = "flat_enriched"
        elif raw:
            fmt = "other"
        else:
            fmt = "empty"

        formats[fmt] = formats.get(fmt, 0) + 1

        # Track top-level keys
        for k in raw.keys():
            top_level_keys[k] = top_level_keys.get(k, 0) + 1

        # Keep 1 sample per format
        if fmt not in samples:
            samples[fmt] = [{
                "id": str(row[0]),
                "top_keys": sorted(raw.keys())[:20],
                "versions_count": len(raw.get("versions", [])) if has_versions else 0,
            }]

    return {
        "analyzed": len(rows),
        "formats": formats,
        "top_level_keys_frequency": dict(sorted(top_level_keys.items(), key=lambda x: -x[1])[:25]),
        "samples": samples,
    }


@router.get("/bosa-can-flat-peek")
def bosa_can_flat_peek(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Peek at flat_enriched CAN notices: show content of lots, noticeIds, dossier fields.
    Helps decide if award data is already present or needs API fetch.
    """
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        raw = row[3]
        if not isinstance(raw, dict):
            try:
                raw = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                raw = {}

        # Skip ones with versions (XML format)
        if "versions" in raw and isinstance(raw.get("versions"), list) and raw["versions"]:
            continue

        item: dict[str, Any] = {
            "id": str(row[0]),
            "source_id": row[1],
            "title": (row[2] or "")[:100],
            "all_keys": sorted(raw.keys()),
            "lots": raw.get("lots"),
            "noticeIds": raw.get("noticeIds"),
            "dossier": raw.get("dossier"),
            "natures": raw.get("natures"),
            "status": raw.get("status"),
            "migrated": raw.get("migrated"),
            "noticeSubType": raw.get("noticeSubType"),
            "organisation_name": raw.get("organisation_name"),
            "organisation": raw.get("organisation"),
        }
        results.append(item)

    return {
        "count": len(results),
        "results": results,
    }


# ── Bulk fetch + enrich via BOSA workspace API ──────────────────────


@router.post(
    "/bosa-enrich-awards-via-api",
    summary="Bulk-enrich flat BOSA CANs via workspace API",
    description=(
        "For each CAN (type 29) without award data and without XML in raw_data:\n"
        "1. GET /publication-workspaces/{source_id} → workspace detail with eForms XML\n"
        "2. Parse XML for award data (winner, value, date, nb tenders)\n"
        "3. Update notice fields + replace raw_data with full workspace response\n\n"
        "Rate-limited with configurable delay between API calls.\n"
        "Use dry_run=true first to see count + estimated time."
    ),
)
def bosa_enrich_awards_via_api(
    limit: int = Query(100, ge=1, le=50000),
    batch_size: int = Query(50, ge=5, le=500),
    api_delay_ms: int = Query(300, ge=50, le=5000),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Bulk-enrich flat BOSA CANs by fetching workspace detail via API.

    For each CAN (type 29) without award data and without XML in raw_data:
    1. GET /publication-workspaces/{source_id} → workspace detail with XML
    2. Parse eForms XML for award data
    3. Update notice fields + replace raw_data with full workspace response

    Rate-limited with configurable delay between API calls.
    """
    import time

    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Count eligible: CAN type 29, no award data
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '')"
    ))
    total_eligible = count_result.scalar()

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "limit": limit,
            "batch_size": batch_size,
            "api_delay_ms": api_delay_ms,
            "dry_run": True,
            "message": "Set dry_run=false to execute. This will make API calls to BOSA.",
            "estimated_time_minutes": round(
                min(total_eligible, limit) * api_delay_ms / 60000, 1
            ),
        }

    # Initialize BOSA API client
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, provider = _get_client()
        if not isinstance(client, OfficialEProcurementClient):
            return {"error": f"BOSA client is not official ({provider}), cannot fetch workspace details"}
    except Exception as e:
        return {"error": f"Failed to initialize BOSA client: {e}"}

    enriched = 0
    skipped_no_xml = 0
    skipped_no_fields = 0
    api_errors = 0
    parse_errors = 0
    already_has_xml = 0
    batches_done = 0
    offset = 0
    delay_sec = api_delay_ms / 1000.0

    while (enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml) < limit:
        # Fetch batch of flat CANs
        rows = db.execute(text(
            "SELECT id, source_id, raw_data FROM notices "
            "WHERE source = 'BOSA_EPROC' "
            "  AND notice_sub_type = '29' "
            "  AND raw_data IS NOT NULL "
            "  AND (award_winner_name IS NULL OR award_winner_name = '') "
            "ORDER BY publication_date DESC, id "
            "LIMIT :batch_size OFFSET :offset"
        ), {"batch_size": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        for row in rows:
            if (enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml) >= limit:
                break

            notice_id = row[0]
            source_id = row[1]
            raw_data = row[2]

            try:
                if not isinstance(raw_data, dict):
                    raw_data = json.loads(raw_data) if raw_data else {}

                # Check if raw_data already has XML (skip API call)
                existing_xml = extract_xml_from_raw_data(raw_data)
                if existing_xml:
                    # Already has XML — parse directly (shouldn't happen often since
                    # bosa_enrich_awards already handled these, but just in case)
                    parsed = parse_award_data(existing_xml)
                    fields = build_notice_fields(parsed)
                    if fields:
                        _update_notice_fields(db, notice_id, fields)
                        enriched += 1
                    else:
                        skipped_no_fields += 1
                    already_has_xml += 1
                    continue

                # Fetch workspace detail via API
                if not source_id:
                    skipped_no_xml += 1
                    continue

                time.sleep(delay_sec)
                workspace_data = client.get_publication_workspace(source_id)

                if not workspace_data:
                    api_errors += 1
                    continue

                # Extract XML from workspace response
                xml_content = extract_xml_from_raw_data(workspace_data)
                if not xml_content:
                    skipped_no_xml += 1
                    continue

                # Parse award data
                parsed = parse_award_data(xml_content)
                fields = build_notice_fields(parsed)

                if not fields:
                    skipped_no_fields += 1
                    continue

                # Update notice: award fields + replace raw_data with full workspace
                _update_notice_fields(db, notice_id, fields)

                # Also update raw_data with the workspace response (has XML for future use)
                db.execute(
                    text("UPDATE notices SET raw_data = :rd WHERE id = :nid"),
                    {
                        "rd": json.dumps(workspace_data, default=str),
                        "nid": notice_id,
                    },
                )
                enriched += 1

            except Exception as e:
                logger.warning(
                    "Award API enrichment error for notice %s (source=%s): %s",
                    notice_id, source_id, e,
                )
                parse_errors += 1

        db.commit()
        batches_done += 1
        offset += batch_size

        processed = enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml
        logger.info(
            "Award API enrichment batch %d: enriched=%d, api_errors=%d, "
            "skipped_no_xml=%d, skipped_no_fields=%d, parse_errors=%d, "
            "already_has_xml=%d (total processed=%d/%d)",
            batches_done, enriched, api_errors,
            skipped_no_xml, skipped_no_fields, parse_errors,
            already_has_xml, processed, total_eligible,
        )

    return {
        "total_eligible": total_eligible,
        "enriched": enriched,
        "skipped_no_xml": skipped_no_xml,
        "skipped_no_fields": skipped_no_fields,
        "api_errors": api_errors,
        "parse_errors": parse_errors,
        "already_has_xml": already_has_xml,
        "batches": batches_done,
        "dry_run": False,
    }


def _update_notice_fields(db: Session, notice_id: str, fields: dict[str, Any]):
    """Update a single notice with parsed award fields."""
    set_clauses = []
    params: dict[str, Any] = {"nid": notice_id}

    if "award_winner_name" in fields:
        set_clauses.append("award_winner_name = :winner")
        params["winner"] = fields["award_winner_name"]
    if "award_value" in fields:
        set_clauses.append("award_value = :value")
        params["value"] = float(fields["award_value"])
    if "award_date" in fields:
        set_clauses.append("award_date = :adate")
        params["adate"] = str(fields["award_date"])
    if "number_tenders_received" in fields:
        set_clauses.append("number_tenders_received = :ntenders")
        params["ntenders"] = fields["number_tenders_received"]
    if "award_criteria_json" in fields:
        set_clauses.append("award_criteria_json = :acjson")
        params["acjson"] = json.dumps(fields["award_criteria_json"], default=str)

    if set_clauses:
        set_clauses.append("updated_at = now()")
        sql = f"UPDATE notices SET {', '.join(set_clauses)} WHERE id = :nid"
        db.execute(text(sql), params)


@router.get(
    "/bosa-enrich-debug",
    summary="Debug: step-by-step workspace fetch + parse for a few CANs",
    description=(
        "Fetches workspace detail + parses XML for up to 20 flat CANs.\n"
        "Shows each step: existing XML check → API fetch → XML extract → parse → fields.\n"
        "Use this to diagnose enrichment failures before running bulk."
    ),
)
def bosa_enrich_debug(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Debug endpoint: fetch workspace + parse for a few CANs and show
    exactly what happens at each step (errors, XML presence, parsed data).
    """
    import time
    import traceback

    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Init client
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, provider = _get_client()
        if not isinstance(client, OfficialEProcurementClient):
            return {"error": f"Not official client: {provider}"}
    except Exception as e:
        return {"error": str(e)}

    # Get flat CANs (no XML in raw_data, no award data)
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit * 3}).fetchall()  # fetch more to skip XML ones

    results = []
    for row in rows:
        if len(results) >= limit:
            break

        notice_id = row[0]
        source_id = row[1]
        title = (row[2] or "")[:80]
        raw_data = row[3]

        item: dict[str, Any] = {
            "id": str(notice_id),
            "source_id": source_id,
            "title": title,
            "steps": {},
        }

        try:
            if not isinstance(raw_data, dict):
                raw_data = json.loads(raw_data) if raw_data else {}

            # Step 1: Check existing XML
            existing_xml = extract_xml_from_raw_data(raw_data)
            if existing_xml:
                item["steps"]["1_existing_xml"] = "FOUND (skipping API)"
                continue  # skip — we want flat ones

            item["steps"]["1_existing_xml"] = "NOT_FOUND (will fetch API)"

            # Step 2: Fetch workspace
            time.sleep(0.3)
            workspace = client.get_publication_workspace(source_id)
            if not workspace:
                item["steps"]["2_api_fetch"] = "FAILED (None returned)"
                results.append(item)
                continue

            ws_keys = sorted(workspace.keys()) if isinstance(workspace, dict) else str(type(workspace))
            item["steps"]["2_api_fetch"] = f"OK — keys: {ws_keys}"

            # Step 3: Extract XML from workspace
            xml_content = extract_xml_from_raw_data(workspace)
            if not xml_content:
                # Check why: does it have versions?
                versions = workspace.get("versions", [])
                version_info = []
                for v in versions:
                    if isinstance(v, dict):
                        notice = v.get("notice")
                        if notice is None:
                            version_info.append("notice=None")
                        elif isinstance(notice, dict):
                            has_xml = bool(notice.get("xmlContent"))
                            version_info.append(f"notice=dict(xmlContent={has_xml})")
                        else:
                            version_info.append(f"notice=type:{type(notice).__name__}")
                    else:
                        version_info.append(f"version=type:{type(v).__name__}")

                item["steps"]["3_extract_xml"] = f"NO XML — {len(versions)} versions: {version_info}"
                results.append(item)
                continue

            item["steps"]["3_extract_xml"] = f"OK — {len(xml_content)} chars"

            # Step 4: Parse award data
            parsed = parse_award_data(xml_content)
            item["steps"]["4_parse"] = {
                "total_amount": str(parsed.get("total_amount")) if parsed.get("total_amount") else None,
                "winners_count": len(parsed.get("winners", [])),
                "tenders_received": parsed.get("tenders_received"),
                "award_date": str(parsed.get("award_date")) if parsed.get("award_date") else None,
            }

            # Step 5: Build fields
            fields = build_notice_fields(parsed)
            item["steps"]["5_fields"] = fields if fields else "EMPTY (no fields generated)"

        except Exception as e:
            item["steps"]["ERROR"] = f"{type(e).__name__}: {e}"
            item["steps"]["traceback"] = traceback.format_exc()[-500:]

        results.append(item)

    return {"count": len(results), "results": results}


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


# ── Phase 2b: Document Portal Crawler ────────────────────────────


@router.post(
    "/crawl-portal-documents",
    tags=["admin"],
    summary="Crawl portal pages to discover and download PDF documents",
    description=(
        "Follows HTML links (publicprocurement.be portals, TED pages, etc.) "
        "to find actual PDF documents. Downloads + extracts text.\n\n"
        "Targets notices that have portal links but no downloaded PDFs.\n"
        "Use dry_run=true first to see count."
    ),
)
def crawl_portal_documents(
    limit: int = Query(50, ge=1, le=1000, description="Max notices to crawl"),
    source: Optional[str] = Query(None, description="Filter: BOSA_EPROC or TED_EU"),
    download: bool = Query(True, description="Download PDFs (false = discover only)"),
    dry_run: bool = Query(True, description="Preview only"),
    db: Session = Depends(get_db),
) -> dict:
    """Crawl procurement portal pages to discover PDF documents."""
    from app.services.document_crawler import batch_crawl_notices
    return batch_crawl_notices(
        db, limit=limit, source=source, download=download, dry_run=dry_run,
    )


@router.post(
    "/crawl-notice/{notice_id}",
    tags=["admin"],
    summary="Crawl portal pages for a single notice",
)
def crawl_single_notice(
    notice_id: str,
    download: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Crawl portal pages for a specific notice to discover PDF documents."""
    from app.services.document_crawler import crawl_portal_for_pdfs
    from sqlalchemy import text as sql_text

    # Find portal URLs for this notice
    rows = db.execute(
        sql_text(
            "SELECT url FROM notice_documents WHERE notice_id = :nid "
            "AND (LOWER(file_type) = 'html' "
            "     OR url LIKE '%publicprocurement.be%' "
            "     OR url LIKE '%e-tendering%')"
        ),
        {"nid": notice_id},
    ).fetchall()

    if not rows:
        return {"status": "no_portal_links", "notice_id": notice_id}

    all_results = []
    for (portal_url,) in rows:
        results = crawl_portal_for_pdfs(db, notice_id, portal_url, download=download)
        all_results.extend(results)

    return {
        "notice_id": notice_id,
        "portal_urls_crawled": len(rows),
        "documents": all_results,
    }
