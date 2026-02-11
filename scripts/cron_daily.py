#!/usr/bin/env python3
"""
Railway cron: daily import + watchlist matching + email digests.

Usage (Railway cron service):
    python scripts/cron_daily.py

Schedule: 0 6 * * * (daily at 06:00 UTC = 07:00 CET)

This script:
  1. Runs Alembic migrations (idempotent)
  2. Imports latest notices from TED + BOSA (last 3 days)
  3. Runs watchlist matcher for all enabled watchlists
  4. Sends email digests for watchlists with new matches

Railway cron setup:
  1. Create a new service in Railway (same repo)
  2. Set start command: python scripts/cron_daily.py
  3. Set schedule: 0 6 * * * (daily at 06:00 UTC)
  4. Attach the same Postgres database
  5. Copy env vars from web service (DATABASE_URL, EMAIL_MODE, RESEND_API_KEY, etc.)
"""
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Project root on path ───────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("cron_daily")

# ── Global timeout (5 min) ─────────────────────────────────────────
TIMEOUT_SECONDS = int(os.environ.get("CRON_TIMEOUT_SECONDS", "300"))


def _timeout_handler(signum, frame):
    logger.error(f"TIMEOUT: cron exceeded {TIMEOUT_SECONDS}s — aborting")
    sys.exit(2)


# signal.alarm is Unix-only; skip gracefully on Windows
if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)


# ── Load all SQLAlchemy models (FK resolution) ─────────────────────
def _load_models():
    """Import every model so SQLAlchemy sees all tables/FKs before any query."""
    import app.models  # noqa: F401  — Base, Notice, Watchlist, etc.
    import app.models.user  # noqa: F401
    import app.models.user_favorite  # noqa: F401
    import app.models.notice  # noqa: F401
    import app.models.notice_detail  # noqa: F401
    import app.models.notice_document  # noqa: F401
    import app.models.notice_lot  # noqa: F401
    import app.models.notice_cpv_additional  # noqa: F401
    import app.models.watchlist  # noqa: F401
    import app.models.watchlist_match  # noqa: F401
    import app.models.filter  # noqa: F401
    import app.models.import_run  # noqa: F401


# ── Step 1: Alembic migrations ─────────────────────────────────────
def step_migrate() -> bool:
    """Run Alembic migrations (idempotent)."""
    logger.info("Step 1/3: Running database migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(f"Migration warning: {result.stderr[:500]}")
    else:
        logger.info("Migrations OK.")
    return True  # non-blocking


# ── Step 2: Import notices (TED + BOSA) ────────────────────────────
def step_import() -> dict:
    """Import latest notices from TED + BOSA."""
    logger.info("Step 2/3: Importing latest notices...")

    _load_models()

    sources = os.environ.get("IMPORT_SOURCES", "BOSA,TED")
    days_back = int(os.environ.get("IMPORT_DAYS_BACK", "3"))
    page_size = int(os.environ.get("IMPORT_PAGE_SIZE", "100"))
    max_pages = int(os.environ.get("IMPORT_MAX_PAGES", "10"))

    from app.connectors.ted_connector import search_ted_notices
    from app.connectors.bosa.client import search_publications
    from app.db.session import SessionLocal
    from app.services.notice_service import NoticeService

    db = SessionLocal()
    stats = {"sources": {}, "total_created": 0, "total_updated": 0, "total_errors": 0}

    try:
        svc = NoticeService(db)
        since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y%m%d")

        for source in [s.strip().upper() for s in sources.split(",") if s.strip()]:
            source_stats = {"created": 0, "updated": 0, "errors": 0, "pages": 0}

            try:
                if source == "TED":
                    page = 1
                    while page <= max_pages:
                        try:
                            result = search_ted_notices(
                                term=f"PD >= {since}",
                                page=page,
                                page_size=page_size,
                            )
                            # Notices are in result["json"]["notices"] or result["notices"]
                            notices = (
                                result.get("notices")
                                or (result.get("json") or {}).get("notices")
                                or []
                            )
                            if not notices:
                                break

                            import_result = _sync_import(
                                svc.import_from_ted_search, notices
                            )
                            source_stats["created"] += import_result.get("created", 0)
                            source_stats["updated"] += import_result.get("updated", 0)
                            source_stats["errors"] += len(import_result.get("errors", []))
                            source_stats["pages"] = page
                            page += 1
                        except Exception as e:
                            logger.error(f"TED page {page} error: {e}")
                            source_stats["errors"] += 1
                            break

                elif source == "BOSA":
                    page = 1
                    while page <= max_pages:
                        try:
                            result = search_publications(
                                term="",
                                page=page,
                                page_size=page_size,
                            )
                            # Items are in result["json"]["publications"|"items"|"results"|"data"]
                            payload = result.get("json") or {}
                            notices = []
                            if isinstance(payload, dict):
                                for key in ("publications", "items", "results", "data"):
                                    candidate = payload.get(key)
                                    if isinstance(candidate, list):
                                        notices = candidate
                                        break
                            if not notices:
                                break

                            import_result = _sync_import(
                                svc.import_from_eproc_search, notices
                            )
                            source_stats["created"] += import_result.get("created", 0)
                            source_stats["updated"] += import_result.get("updated", 0)
                            source_stats["errors"] += len(import_result.get("errors", []))
                            source_stats["pages"] = page
                            page += 1
                        except Exception as e:
                            logger.error(f"BOSA page {page} error: {e}")
                            source_stats["errors"] += 1
                            break

                logger.info(
                    f"  {source}: +{source_stats['created']} created, "
                    f"~{source_stats['updated']} updated, "
                    f"!{source_stats['errors']} errors "
                    f"({source_stats['pages']} pages)"
                )

            except Exception as e:
                logger.error(f"  {source} connector failed: {e}")
                source_stats["errors"] += 1

            stats["sources"][source] = source_stats
            stats["total_created"] += source_stats["created"]
            stats["total_updated"] += source_stats["updated"]
            stats["total_errors"] += source_stats["errors"]

    finally:
        db.close()

    logger.info(
        f"Import done: +{stats['total_created']} created, "
        f"~{stats['total_updated']} updated, "
        f"!{stats['total_errors']} errors"
    )
    return stats


def _sync_import(async_import_fn, items: list) -> dict:
    """Run an async import method (import_from_ted_search / import_from_eproc_search)
    synchronously from the cron script."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(async_import_fn(items))
    finally:
        loop.close()


# ── Step 3: Watchlist matching + email digests ──────────────────────
def step_watchlists() -> dict:
    """Run watchlist matching + send email digests."""
    logger.info("Step 3/3: Running watchlist matcher + email digests...")

    _load_models()

    from app.db.session import SessionLocal
    from app.services.watchlist_matcher import run_watchlist_matcher

    db = SessionLocal()
    try:
        results = run_watchlist_matcher(db)
        logger.info(
            f"Watchlists: {results['watchlists_processed']} processed, "
            f"{results['total_new_matches']} new matches, "
            f"{results['emails_sent']} emails sent"
        )
        for detail in results.get("details", []):
            name = detail.get("watchlist_name", "?")
            new = detail.get("new_matches", 0)
            sent = "✉️" if detail.get("email_sent") else ""
            err = f" ⚠️ {detail['email_error']}" if detail.get("email_error") else ""
            if new > 0 or err:
                logger.info(f"  {name}: {new} matches {sent}{err}")
        return results
    finally:
        db.close()


# ── Main entry point ───────────────────────────────────────────────
def main() -> int:
    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info(f"ProcureWatch daily cron started at {start.isoformat()}")
    logger.info("=" * 60)

    exit_code = 0

    # Step 1: Migrate
    try:
        step_migrate()
    except Exception as e:
        logger.error(f"Migration failed (non-blocking): {e}")

    # Step 2: Import
    try:
        import_stats = step_import()
    except Exception as e:
        logger.error(f"Import failed: {e}")
        import_stats = {"error": str(e)}
        exit_code = 1

    # Step 3: Watchlist matching + emails
    try:
        wl_stats = step_watchlists()
    except Exception as e:
        logger.error(f"Watchlist matcher failed: {e}")
        wl_stats = {"error": str(e)}
        exit_code = 1

    # Cancel timeout
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(f"Cron complete in {elapsed:.1f}s (exit={exit_code})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
