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
    """Execute the full import pipeline using bulk_import service."""
    from app.db.session import SessionLocal
    from app.services.bulk_import import bulk_import_all

    started_at = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        result = bulk_import_all(
            db,
            sources=settings.import_sources,
            term=settings.import_term,
            page_size=settings.import_page_size,
            max_pages=settings.import_max_pages,
            fetch_details=False,
            run_backfill=settings.backfill_after_import,
            run_matcher=True,
        )
        result["trigger"] = "scheduler"

        logger.info(
            "[Scheduler] Pipeline done: created=%d updated=%d elapsed=%.1fs",
            result.get("total_created", 0),
            result.get("total_updated", 0),
            result.get("elapsed_seconds", 0),
        )

    except Exception as e:
        result = {
            "status": "error",
            "error": str(e),
            "started_at": started_at.isoformat(),
        }
        logger.exception("[Scheduler] Pipeline failed")
    finally:
        db.close()

    _last_run["import_pipeline"] = result


def _fetch_page(source: str, term: str, page: int, page_size: int) -> list[dict]:
    """Fetch one page from BOSA or TED connector (kept for backward compat)."""
    if source == "BOSA":
        from app.connectors.bosa.client import search_publications
        resp = search_publications(term=term, page=page, page_size=page_size)
        if isinstance(resp, dict):
            payload = resp.get("json") or resp
            if isinstance(payload, dict):
                for key in ("publications", "items", "results", "data"):
                    candidate = payload.get(key)
                    if isinstance(candidate, list):
                        return candidate
            return resp.get("publications", resp.get("items", []))
        return resp if isinstance(resp, list) else []
    elif source == "TED":
        from app.connectors.ted.client import search_ted_notices
        resp = search_ted_notices(term=term, page=page, page_size=page_size)
        if isinstance(resp, dict):
            return resp.get("notices") or (resp.get("json") or {}).get("notices") or []
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
