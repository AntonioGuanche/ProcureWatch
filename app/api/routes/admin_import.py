"""Import, bulk-import, import-runs, scheduler, raw-data diagnostics."""
import asyncio
import json
import logging
import time
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
    tags=["import"],
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


