#!/usr/bin/env python3
"""
Production daily import script: BOSA + TED notices.
Paginates through pages, saves stats to import_runs, optional email alert on high error rate.

Requires: alembic upgrade head (migration 011 creates import_runs table).
Optional: IMPORT_ALERT_EMAIL for high-error-rate alerts.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.notifications.emailer import send_email
from app.services.notice_service import NoticeService

# Logging
CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
FILE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_file: Path, console_level: int = logging.INFO, file_level: int = logging.DEBUG) -> logging.Logger:
    """Console INFO, file DEBUG. Returns root logger."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FMT))
    root.addHandler(ch)
    # File
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(file_level)
    fh.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FMT))
    root.addHandler(fh)
    return root


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Daily import of BOSA and TED notices. BOSA API requires a non-empty search term.",
        epilog="Example: python scripts/import_daily.py --sources BOSA --term construction --days-back 7 --page-size 5 --max-pages 1",
    )
    p.add_argument("--sources", default="BOSA,TED", help="Comma-separated: BOSA,TED (default: BOSA,TED)")
    p.add_argument(
        "--term",
        default="*",
        help="Search term for BOSA and TED. BOSA requires non-empty term (default: * for broad match; use e.g. 'construction' for specific)",
    )
    p.add_argument("--days-back", type=int, default=7, help="Import notices from last N days (default: 7)")
    p.add_argument("--page-size", type=int, default=100, help="Page size (default: 100)")
    p.add_argument("--max-pages", type=int, default=10, help="Max pages per source (default: 10)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be imported, do not commit")
    p.add_argument("--log-file", type=Path, default=Path("logs/import_daily.log"), help="Log file path")
    return p.parse_args()


def date_range(days_back: int) -> tuple[date, date]:
    """Return (publication_date_from, publication_date_to) as today - days_back to today."""
    today = date.today()
    from_date = today - timedelta(days=days_back)
    return from_date, today


def ted_date_query(date_from: date, date_to: date) -> str:
    """TED expert query for publication date range (for reference; not used in search to avoid API errors)."""
    return f'(publication-date >= "{date_from.isoformat()}") AND (publication-date <= "{date_to.isoformat()}")'


def _ted_term(term: str) -> str:
    """
    Normalize term for TED search. Pass the same keyword as BOSA so search_ted_notices(term=...)
    works like test_import_ted.py (client's build_expert_query turns it into a valid expert query).
    Avoid passing a combined date+term expert query - the API can reject it.
    """
    raw = (term or "*").strip() or "*"
    return raw


def fetch_bosa_page(page: int, page_size: int, term: str, logger: logging.Logger) -> tuple[list, int, bool]:
    """Fetch one page of BOSA results. Returns (items, total_approx, network_error). BOSA requires non-empty term."""
    from connectors.eprocurement.client import search_publications

    search_term = (term or "*").strip() or "*"
    try:
        result = search_publications(term=search_term, page=page, page_size=page_size)
    except Exception as e:
        logger.debug("BOSA search error: %s", e)
        return [], 0, True
    payload = result.get("json") or {}
    if not isinstance(payload, dict):
        return [], 0, False
    for key in ("publications", "items", "results", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            total = result.get("metadata") or {}
            total = total.get("totalCount") or payload.get("totalCount") or len(candidate)
            return candidate, int(total) if total is not None else len(candidate), False
    return [], 0, False


def fetch_ted_page(term: str, page: int, page_size: int, logger: logging.Logger) -> tuple[list, int, bool]:
    """Fetch one page of TED results. Returns (notices, total_approx, network_error)."""
    from connectors.ted.client import search_ted_notices

    try:
        result = search_ted_notices(term=term, page=page, page_size=page_size)
    except Exception as e:
        logger.debug("TED search error: %s", e)
        return [], 0, True
    notices = result.get("notices") or (result.get("json") or {}).get("notices") or []
    if not isinstance(notices, list):
        notices = []
    meta = result.get("metadata") or {}
    j = result.get("json") or {}
    total = meta.get("totalCount") or j.get("totalNoticeCount") or j.get("totalCount") or len(notices)
    return notices, int(total) if total is not None else len(notices), False


def save_import_run(
    db,
    run_id: str,
    source: str,
    started_at: datetime,
    completed_at: datetime,
    created_count: int,
    updated_count: int,
    error_count: int,
    errors_json: list | None,
    search_criteria_json: dict,
) -> None:
    """Insert one row into import_runs."""
    # Store JSON as string for portability (SQLite/Postgres)
    errors_ser = json.dumps(errors_json, default=str) if errors_json else None
    criteria_ser = json.dumps(search_criteria_json, default=str) if search_criteria_json else None
    db.execute(
        text("""
            INSERT INTO import_runs
            (id, source, started_at, completed_at, created_count, updated_count, error_count, errors_json, search_criteria_json)
            VALUES (:id, :source, :started_at, :completed_at, :created_count, :updated_count, :error_count, :errors_json, :search_criteria_json)
        """),
        {
            "id": run_id,
            "source": source,
            "started_at": started_at,
            "completed_at": completed_at,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors_json": errors_ser,
            "search_criteria_json": criteria_ser,
        },
    )
    db.commit()


def run_source(
    source: str,
    date_from: date,
    date_to: date,
    term: str,
    page_size: int,
    max_pages: int,
    dry_run: bool,
    logger: logging.Logger,
) -> tuple[int, int, int, list, dict]:
    """Run import for one source (BOSA or TED). Returns (created, updated, error_count, errors_list, search_criteria)."""
    search_criteria = {
        "term": (term or "*").strip() or "*",
        "publication_date_from": date_from.isoformat(),
        "publication_date_to": date_to.isoformat(),
        "page_size": page_size,
    }
    total_created, total_updated, total_errors = 0, 0, 0
    all_errors: list = []
    db = SessionLocal()
    service = NoticeService(db)

    try:
        for page in range(1, max_pages + 1):
            if source == "BOSA":
                items, _total, network_err = fetch_bosa_page(page, page_size, term, logger)
                if network_err:
                    logger.warning("[BOSA] Network error on page %s, retrying once", page)
                    items, _total, network_err = fetch_bosa_page(page, page_size, term, logger)
                    if network_err:
                        all_errors.append({"message": "BOSA search failed after retry"})
                        total_errors += 1
                        break
            else:
                ted_term = _ted_term(term)
                items, _total, network_err = fetch_ted_page(ted_term, page, page_size, logger)
                if network_err:
                    logger.warning("[TED] Network error on page %s, retrying once", page)
                    items, _total, network_err = fetch_ted_page(ted_term, page, page_size, logger)
                    if network_err:
                        all_errors.append({"message": "TED search failed after retry"})
                        total_errors += 1
                        break
            if not items:
                logger.debug("[%s] Page %s: 0 items, stopping", source, page)
                break
            logger.info("[%s] Page %s/%s: %s items", source, page, max_pages, len(items))
            if dry_run:
                total_created += len(items)
                continue
            try:
                if source == "BOSA":
                    stats = asyncio.run(service.import_from_eproc_search(items, fetch_details=False))
                else:
                    stats = asyncio.run(service.import_from_ted_search(items, fetch_details=False))
                total_created += stats["created"]
                total_updated += stats["updated"]
                errs = stats.get("errors") or []
                total_errors += len(errs)
                all_errors.extend(errs)
            except Exception as e:
                logger.exception("[%s] Import failed for page %s: %s", source, page, e)
                total_errors += 1
                all_errors.append({"message": str(e), "page": page})
                continue
    finally:
        db.close()

    return total_created, total_updated, total_errors, all_errors, search_criteria


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.log_file)
    sources = [s.strip().upper() for s in args.sources.split(",") if s.strip()]
    if not sources:
        sources = ["BOSA", "TED"]
    date_from, date_to = date_range(args.days_back)

    logger.info("Starting daily import (sources: %s, term: %r)", ", ".join(sources), args.term)
    logger.info("Date range: %s to %s", date_from, date_to)
    if args.dry_run:
        logger.info("DRY RUN: no data will be committed")

    total_created, total_updated, total_errors = 0, 0, 0
    run_ids: list[str] = []
    started_at = datetime.now(timezone.utc)

    for source in sources:
        if source not in ("BOSA", "TED"):
            logger.warning("Skipping unknown source: %s", source)
            continue
        run_id = str(uuid.uuid4())
        run_ids.append(run_id)
        run_start = datetime.now(timezone.utc)
        created, updated, err_count, errors_list, criteria = run_source(
            source, date_from, date_to, args.term, args.page_size, args.max_pages, args.dry_run, logger
        )
        run_end = datetime.now(timezone.utc)
        total_created += created
        total_updated += updated
        total_errors += err_count
        logger.info(
            "[%s] Completed: Created %s, Updated %s, Errors %s",
            source, created, updated, err_count,
        )
        if not args.dry_run:
            try:
                db = SessionLocal()
                save_import_run(
                    db,
                    run_id=run_id,
                    source=source,
                    started_at=run_start,
                    completed_at=run_end,
                    created_count=created,
                    updated_count=updated,
                    error_count=err_count,
                    errors_json=errors_list if errors_list else None,
                    search_criteria_json=criteria,
                )
                db.close()
            except Exception as e:
                logger.exception("Failed to save import_runs row: %s", e)

    # Summary
    logger.info(
        "Daily import completed. Total: %s created, %s updated",
        total_created, total_updated,
    )
    if not args.dry_run:
        logger.info("Stats saved to import_runs table")

    # Error rate alert
    processed = total_created + total_updated + total_errors
    if processed > 0 and total_errors > 0:
        error_rate = total_errors / processed
        if error_rate > 0.10:
            alert_to = os.environ.get("IMPORT_ALERT_EMAIL") or getattr(settings, "import_alert_email", None) or ""
            if alert_to:
                try:
                    send_email(
                        to=alert_to,
                        subject="[ProcureWatch] Daily import: high error rate",
                        body=f"Error rate: {error_rate:.1%} ({total_errors} errors / {processed} processed).\nSources: {', '.join(sources)}.\nCheck logs: {args.log_file}",
                    )
                    logger.info("Alert email sent to %s", alert_to)
                except Exception as e:
                    logger.warning("Failed to send alert email: %s", e)
            else:
                logger.warning("IMPORT_ALERT_EMAIL not set; skipping email alert (error rate %.1f%%)", error_rate * 100)

    # Exit codes: 0 success, 1 partial (some errors), 2 total failure
    if total_created == 0 and total_updated == 0 and total_errors > 0 and not args.dry_run:
        return 2
    if total_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
