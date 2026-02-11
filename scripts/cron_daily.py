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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("cron_daily")


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


def step_import() -> dict:
    """Import latest notices from TED + BOSA."""
    logger.info("Step 2/3: Importing latest notices...")

    sources = os.environ.get("IMPORT_SOURCES", "BOSA,TED")
    days_back = int(os.environ.get("IMPORT_DAYS_BACK", "3"))
    page_size = int(os.environ.get("IMPORT_PAGE_SIZE", "100"))
    max_pages = int(os.environ.get("IMPORT_MAX_PAGES", "10"))

    # Use import_daily's logic directly
    from app.db.session import SessionLocal
    from app.services.notice_service import NoticeService

    db = SessionLocal()
    stats = {"sources": {}, "total_created": 0, "total_updated": 0, "total_errors": 0}

    try:
        svc = NoticeService(db)

        for source in [s.strip().upper() for s in sources.split(",") if s.strip()]:
            source_stats = {"created": 0, "updated": 0, "errors": 0, "pages": 0}

            try:
                if source == "TED":
                    from app.connectors.ted import TedConnector
                    connector = TedConnector()
                    from datetime import timedelta
                    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y%m%d")

                    page = 1
                    while page <= max_pages:
                        try:
                            results = connector.search(
                                query=f"PD >= {since}",
                                page=page,
                                page_size=page_size,
                            )
                            notices = results.get("notices", [])
                            if not notices:
                                break
                            for n in notices:
                                try:
                                    _, created = svc.upsert_from_connector(n, source="ted_eu")
                                    if created:
                                        source_stats["created"] += 1
                                    else:
                                        source_stats["updated"] += 1
                                except Exception as e:
                                    source_stats["errors"] += 1
                                    logger.debug(f"TED upsert error: {e}")
                            source_stats["pages"] = page
                            page += 1
                        except Exception as e:
                            logger.error(f"TED page {page} error: {e}")
                            source_stats["errors"] += 1
                            break

                elif source == "BOSA":
                    from app.connectors.bosa import BosaConnector
                    connector = BosaConnector()

                    page = 1
                    while page <= max_pages:
                        try:
                            results = connector.search(page=page, page_size=page_size)
                            notices = results.get("notices", [])
                            if not notices:
                                break
                            for n in notices:
                                try:
                                    _, created = svc.upsert_from_connector(n, source="bosa_eproc")
                                    if created:
                                        source_stats["created"] += 1
                                    else:
                                        source_stats["updated"] += 1
                                except Exception as e:
                                    source_stats["errors"] += 1
                                    logger.debug(f"BOSA upsert error: {e}")
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


def step_watchlists() -> dict:
    """Run watchlist matching + send email digests."""
    logger.info("Step 3/3: Running watchlist matcher + email digests...")

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

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(f"Cron complete in {elapsed:.1f}s (exit={exit_code})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
