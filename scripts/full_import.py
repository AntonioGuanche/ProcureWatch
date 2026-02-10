"""
Full historical import script.

Run locally:    python scripts/full_import.py
Run on Railway: railway run python scripts/full_import.py

Imports TED month-by-month from a start date, and all BOSA pages.
"""
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("full_import")


def run_full_import(
    ted_start: str = "2025-01-01",
    ted_base_term: str = "notice-type = cn*",
    bosa_term: str = "*",
    page_size: int = 200,
    max_pages_per_month: int = 50,
    bosa_max_pages: int = 80,
    run_bosa: bool = True,
    run_ted: bool = True,
    run_backfill: bool = True,
) -> dict:
    """Run full historical import."""
    from app.db.session import SessionLocal
    from app.services.bulk_import import bulk_import_source

    db = SessionLocal()
    started = datetime.now(timezone.utc)
    results = {
        "started_at": started.isoformat(),
        "ted_months": [],
        "bosa": None,
        "totals": {"created": 0, "updated": 0, "skipped": 0, "errors": 0},
    }

    try:
        # ── TED: month by month ──
        if run_ted:
            start = date.fromisoformat(ted_start)
            today = date.today()
            current = start.replace(day=1)

            while current <= today:
                # Month boundaries
                month_start = current.strftime("%Y%m%d")
                # Last day of month
                if current.month == 12:
                    next_month = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    next_month = current.replace(month=current.month + 1, day=1)
                month_end = (next_month - timedelta(days=1)).strftime("%Y%m%d")

                term = f"{ted_base_term} AND PD >= {month_start} AND PD <= {month_end}"
                label = current.strftime("%Y-%m")

                logger.info("═══ TED %s ═══ term: %s", label, term)

                try:
                    stats = bulk_import_source(
                        db,
                        source="TED",
                        term=term,
                        page_size=page_size,
                        max_pages=max_pages_per_month,
                        fetch_details=False,
                    )
                    created = stats.get("total_created", 0)
                    updated = stats.get("total_updated", 0)
                    skipped = stats.get("total_skipped", 0)
                    errors = stats.get("total_errors", 0)
                    pages = stats.get("pages_fetched", 0)
                    api_total = stats.get("api_total_count")

                    results["ted_months"].append({
                        "month": label,
                        "api_total": api_total,
                        "pages_fetched": pages,
                        "created": created,
                        "updated": updated,
                        "skipped": skipped,
                        "errors": errors,
                        "elapsed": stats.get("elapsed_seconds", 0),
                    })
                    results["totals"]["created"] += created
                    results["totals"]["updated"] += updated
                    results["totals"]["skipped"] += skipped
                    results["totals"]["errors"] += errors

                    logger.info(
                        "  → %s: %s total, %d pages, +%d new, %d updated (%.1fs)",
                        label, api_total, pages, created, updated,
                        stats.get("elapsed_seconds", 0),
                    )
                except Exception as e:
                    logger.error("  → %s FAILED: %s", label, e)
                    results["ted_months"].append({"month": label, "error": str(e)})

                current = next_month

        # ── BOSA: all pages ──
        if run_bosa:
            logger.info("═══ BOSA (all pages, term='%s') ═══", bosa_term)
            try:
                stats = bulk_import_source(
                    db,
                    source="BOSA",
                    term=bosa_term,
                    page_size=page_size,
                    max_pages=bosa_max_pages,
                    fetch_details=False,
                )
                results["bosa"] = {
                    "api_total": stats.get("api_total_count"),
                    "pages_fetched": stats.get("pages_fetched", 0),
                    "created": stats.get("total_created", 0),
                    "updated": stats.get("total_updated", 0),
                    "skipped": stats.get("total_skipped", 0),
                    "errors": stats.get("total_errors", 0),
                    "elapsed": stats.get("elapsed_seconds", 0),
                }
                results["totals"]["created"] += stats.get("total_created", 0)
                results["totals"]["updated"] += stats.get("total_updated", 0)
                logger.info(
                    "  → BOSA: %s total, %d pages, +%d new, %d updated (%.1fs)",
                    stats.get("api_total_count"), stats.get("pages_fetched", 0),
                    stats.get("total_created", 0), stats.get("total_updated", 0),
                    stats.get("elapsed_seconds", 0),
                )
            except Exception as e:
                logger.error("  → BOSA FAILED: %s", e)
                results["bosa"] = {"error": str(e)}

        # ── Document backfill ──
        if run_backfill and results["totals"]["created"] > 0:
            logger.info("═══ Document backfill ═══")
            try:
                from app.services.document_extraction import backfill_documents_for_all
                bf = backfill_documents_for_all(db, source=None, replace=False)
                results["document_backfill"] = bf
                logger.info("  → Documents: %d created for %d notices",
                           bf.get("documents_created", 0), bf.get("notices_with_docs", 0))
            except Exception as e:
                logger.error("  → Backfill failed: %s", e)
                results["document_backfill_error"] = str(e)

        # ── Watchlist matcher ──
        if results["totals"]["created"] > 0:
            logger.info("═══ Watchlist matcher ═══")
            try:
                from app.services.watchlist_matcher import run_watchlist_matcher
                matcher = run_watchlist_matcher(db)
                results["watchlist_matcher"] = matcher
                logger.info("  → Matcher: %s", matcher)
            except Exception as e:
                logger.error("  → Matcher failed: %s", e)

    finally:
        db.close()

    completed = datetime.now(timezone.utc)
    results["completed_at"] = completed.isoformat()
    results["elapsed_seconds"] = round((completed - started).total_seconds(), 1)

    logger.info(
        "══════════════════════════════════════════════════════\n"
        "  DONE: +%d created, %d updated in %.0f seconds\n"
        "══════════════════════════════════════════════════════",
        results["totals"]["created"],
        results["totals"]["updated"],
        results["elapsed_seconds"],
    )

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Full historical import")
    parser.add_argument("--ted-start", default="2025-01-01", help="TED start date (YYYY-MM-DD)")
    parser.add_argument("--page-size", type=int, default=200, help="Results per page")
    parser.add_argument("--no-bosa", action="store_true", help="Skip BOSA import")
    parser.add_argument("--no-ted", action="store_true", help="Skip TED import")
    parser.add_argument("--no-backfill", action="store_true", help="Skip document backfill")
    parser.add_argument("--ted-only-month", help="Import only this TED month (YYYY-MM)")
    args = parser.parse_args()

    # Override TED start if specific month requested
    ted_start = args.ted_start
    if args.ted_only_month:
        ted_start = f"{args.ted_only_month}-01"

    result = run_full_import(
        ted_start=ted_start,
        page_size=args.page_size,
        run_bosa=not args.no_bosa,
        run_ted=not args.no_ted,
        run_backfill=not args.no_backfill,
    )

    import json
    # Print summary (not full pages detail)
    summary = {k: v for k, v in result.items() if k != "ted_months"}
    summary["ted_months_count"] = len(result.get("ted_months", []))
    summary["ted_months_summary"] = [
        f"{m['month']}: +{m.get('created',0)}" for m in result.get("ted_months", []) if "month" in m
    ]
    print("\n" + json.dumps(summary, indent=2, default=str))
