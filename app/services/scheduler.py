"""Scheduler service: periodic import + watchlist matcher + backfill.

Uses APScheduler to run background jobs within the FastAPI process.
Controlled entirely via environment variables.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobEvent
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level scheduler instance
_scheduler: Optional[BackgroundScheduler] = None
_last_run: dict[str, Any] = {}


def _run_import_pipeline() -> None:
    """Execute the full import pipeline: fetch → save → match → backfill."""
    from app.db.session import SessionLocal
    from app.services.notice_service import NoticeService

    started_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {"started_at": started_at.isoformat(), "status": "running"}

    db = SessionLocal()
    try:
        svc = NoticeService(db)
        sources = [s.strip().upper() for s in settings.import_sources.split(",") if s.strip()]
        term = settings.import_term
        page_size = settings.import_page_size
        max_pages = settings.import_max_pages

        import_results: dict[str, Any] = {}

        for source in sources:
            source_stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

            for page in range(1, max_pages + 1):
                try:
                    items = _fetch_page(source, term, page, page_size)
                    if not items:
                        break

                    if source == "BOSA":
                        import asyncio
                        stats = asyncio.run(
                            svc.import_from_eproc_search(items, fetch_details=False)
                        )
                    elif source == "TED":
                        import asyncio
                        stats = asyncio.run(
                            svc.import_from_ted_search(items, fetch_details=False)
                        )
                    else:
                        logger.warning("Unknown source in scheduler: %s", source)
                        break

                    source_stats["created"] += stats.get("created", 0)
                    source_stats["updated"] += stats.get("updated", 0)
                    source_stats["skipped"] += stats.get("skipped", 0)
                    source_stats["errors"].extend(stats.get("errors", []))

                except Exception as e:
                    source_stats["errors"].append({"page": page, "error": str(e)})
                    logger.exception("[Scheduler] %s page %d failed", source, page)

            import_results[source.lower()] = source_stats

        total_created = sum(r.get("created", 0) for r in import_results.values())
        total_updated = sum(r.get("updated", 0) for r in import_results.values())

        result["import"] = import_results
        result["total_created"] = total_created
        result["total_updated"] = total_updated

        # Run watchlist matcher if new notices
        if total_created > 0:
            try:
                from app.services.watchlist_matcher import run_watchlist_matcher
                matcher = run_watchlist_matcher(db)
                result["watchlist_matcher"] = matcher
                logger.info(
                    "[Scheduler] Matcher: %d watchlists, %d matches, %d emails",
                    matcher.get("watchlists_processed", 0),
                    matcher.get("total_new_matches", 0),
                    matcher.get("emails_sent", 0),
                )
            except Exception as e:
                result["watchlist_matcher_error"] = str(e)
                logger.exception("[Scheduler] Watchlist matcher failed")

        # Backfill if enabled and new data
        if settings.backfill_after_import and (total_created > 0 or total_updated > 0):
            try:
                from app.services.enrichment_service import backfill_from_raw_data, refresh_search_vectors
                bf = backfill_from_raw_data(db)
                result["backfill"] = bf
                if bf.get("enriched", 0) > 0:
                    rows = refresh_search_vectors(db)
                    result["search_vectors_refreshed"] = rows
            except Exception as e:
                result["backfill_error"] = str(e)
                logger.exception("[Scheduler] Backfill failed")

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        result["elapsed_seconds"] = round(elapsed, 1)
        result["status"] = "ok"

        logger.info(
            "[Scheduler] Pipeline done: created=%d updated=%d elapsed=%.1fs",
            total_created, total_updated, elapsed,
        )

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.exception("[Scheduler] Pipeline failed")
    finally:
        db.close()

    _last_run["import_pipeline"] = result


def _fetch_page(source: str, term: str, page: int, page_size: int) -> list[dict]:
    """Fetch one page from BOSA or TED connector."""
    if source == "BOSA":
        from app.connectors.bosa.client import search_publications
        resp = search_publications(term=term, page=page, page_size=page_size)
        if isinstance(resp, dict):
            return resp.get("publications", resp.get("items", []))
        return resp if isinstance(resp, list) else []
    elif source == "TED":
        from app.connectors.ted.client import search_ted_notices
        resp = search_ted_notices(term=term, page=page, page_size=page_size)
        if isinstance(resp, dict):
            return resp.get("notices", resp.get("items", []))
        return resp if isinstance(resp, list) else []
    return []


def _on_job_event(event: JobEvent) -> None:
    """Log scheduler job events."""
    if event.exception:
        logger.error("[Scheduler] Job %s failed: %s", event.job_id, event.exception)
    else:
        logger.info("[Scheduler] Job %s executed OK", event.job_id)


def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start the scheduler if enabled. Called from FastAPI lifespan."""
    global _scheduler

    if not settings.scheduler_enabled:
        logger.info("[Scheduler] Disabled (SCHEDULER_ENABLED=false)")
        return None

    if _scheduler and _scheduler.running:
        logger.warning("[Scheduler] Already running")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_listener(_on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    interval = max(5, settings.import_interval_minutes)

    _scheduler.add_job(
        _run_import_pipeline,
        trigger="interval",
        minutes=interval,
        id="import_pipeline",
        name=f"Import pipeline (every {interval}min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    _scheduler.start()
    logger.info(
        "[Scheduler] Started — import every %d min, sources=%s, pages=%d×%d",
        interval, settings.import_sources, settings.import_max_pages, settings.import_page_size,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully stop the scheduler. Called from FastAPI lifespan."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
    _scheduler = None


def get_scheduler_status() -> dict[str, Any]:
    """Return current scheduler status for admin endpoint."""
    if not settings.scheduler_enabled:
        return {"enabled": False, "message": "Set SCHEDULER_ENABLED=true to activate"}

    running = _scheduler is not None and _scheduler.running if _scheduler else False

    jobs = []
    if _scheduler and running:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

    return {
        "enabled": True,
        "running": running,
        "config": {
            "import_interval_minutes": settings.import_interval_minutes,
            "import_sources": settings.import_sources,
            "import_term": settings.import_term,
            "import_page_size": settings.import_page_size,
            "import_max_pages": settings.import_max_pages,
            "backfill_after_import": settings.backfill_after_import,
        },
        "jobs": jobs,
        "last_run": _last_run.get("import_pipeline"),
    }
