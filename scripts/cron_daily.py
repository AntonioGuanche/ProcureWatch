#!/usr/bin/env python3
"""
Railway cron: full nightly pipeline + email digests.

Usage (Railway cron service):
    python scripts/cron_daily.py

Schedule: 0 4 * * * (daily at 04:00 UTC = 05:00 CET)
  → Pipeline finishes ~04:30, digest emails sent at end.

This script runs ALL nightly steps in-process:
  1. Alembic migrations (idempotent)
  2. Import BOSA + TED (3 days, up to 7500 notices)
  3. Backfill (raw_data → structured fields, optimized)
  4. TED CAN enrich (batch API, ~30s/500 notices)
  5. BOSA enrich awards (XML + API, capped at 20 min)
  6. Merge + cleanup orphan CANs
  7. TED document backfill (catalog URLs)
  8. Watchlist matcher + rescore + email digests

Railway cron setup:
  1. Use existing procurewatch-api cron service
  2. Set start command: python scripts/cron_daily.py
  3. Set schedule: 0 4 * * * (daily at 04:00 UTC)
  4. Attach the same Postgres database
  5. Copy env vars from web service
  6. Set CRON_TIMEOUT_SECONDS=3600 (1 hour)
"""
import logging
import os
import signal
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
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

# ── Global timeout (default 1 hour) ──────────────────────────────
TIMEOUT_SECONDS = int(os.environ.get("CRON_TIMEOUT_SECONDS", "3600"))

def _timeout_handler(signum, frame):
    logger.error(f"TIMEOUT: cron exceeded {TIMEOUT_SECONDS}s — aborting")
    sys.exit(2)

if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)


# ── Load all SQLAlchemy models (FK resolution) ─────────────────────
def _load_models():
    """Import every model so SQLAlchemy sees all tables/FKs before any query."""
    import app.models  # noqa: F401
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


def _elapsed(start: datetime) -> str:
    """Return elapsed time since start as string."""
    secs = (datetime.now(timezone.utc) - start).total_seconds()
    return f"{secs / 60:.1f}min"


# ═════════════════════════════════════════════════════════════════════
# STEP 1: Alembic migrations
# ═════════════════════════════════════════════════════════════════════
def step_migrate() -> bool:
    logger.info("=" * 60)
    logger.info("STEP 1/8: Database migrations")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.warning(f"Migration warning: {result.stderr[:500]}")
    else:
        logger.info("  Migrations OK.")
    return True


# ═════════════════════════════════════════════════════════════════════
# STEP 2: Import BOSA + TED
# ═════════════════════════════════════════════════════════════════════
def step_import(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 2/8: Import BOSA + TED (3 days)")
    from app.services.bulk_import import bulk_import_all

    result = bulk_import_all(
        db,
        sources="BOSA,TED",
        term="*",
        ted_days_back=3,
        page_size=250,
        max_pages=30,
        fetch_details=False,
        run_backfill=False,   # We do it separately in step 3
        run_matcher=False,    # We do it in step 9
    )
    for src_name, src_data in result.get("sources", {}).items():
        logger.info(
            "  %s: api=%s created=%s updated=%s",
            src_name.upper(),
            src_data.get("api_total_count", "?"),
            src_data.get("total_created", 0),
            src_data.get("total_updated", 0),
        )
    return result


# ═════════════════════════════════════════════════════════════════════
# STEP 3: Backfill (raw_data → structured fields)
# ═════════════════════════════════════════════════════════════════════
def step_backfill(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 3/8: Backfill (raw_data → structured fields)")
    from app.services.enrichment_service import backfill_from_raw_data, refresh_search_vectors

    total_enriched = 0
    for pass_num in range(1, 4):  # max 3 passes
        result = backfill_from_raw_data(db, limit=10000)
        enriched = result.get("enriched", 0)
        total_enriched += enriched
        logger.info(
            "  Pass %d: enriched=%d processed=%d",
            pass_num, enriched, result.get("processed", 0),
        )
        if enriched == 0:
            break

    if total_enriched > 0:
        rows = refresh_search_vectors(db)
        logger.info("  Search vectors refreshed (%d rows)", rows)

    return {"total_enriched": total_enriched}


# ═════════════════════════════════════════════════════════════════════
# STEP 4: TED CAN enrich (batch API)
# ═════════════════════════════════════════════════════════════════════
def step_ted_can_enrich(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 4/8: TED CAN Enrich (batch)")
    from app.services.ted_award_enrichment import enrich_ted_can_batch

    total_enriched = 0
    pass_num = 0

    while True:
        pass_num += 1
        result = enrich_ted_can_batch(
            db, limit=500, api_delay_ms=300, dry_run=False,
        )
        enriched = result.get("enriched", 0)
        candidates = result.get("total_candidates", 0)
        total_enriched += enriched
        logger.info(
            "  Pass %d: candidates=%d enriched=%d total=%d",
            pass_num, candidates, enriched, total_enriched,
        )
        if candidates == 0 or enriched == 0:
            break
        if candidates < 500:
            break
        _time.sleep(1)

    return {"total_enriched": total_enriched, "passes": pass_num}


# ═════════════════════════════════════════════════════════════════════
# STEP 5: BOSA enrich awards (XML + API, capped at 20 min)
# ═════════════════════════════════════════════════════════════════════
def step_bosa_enrich(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 5/8: BOSA Enrich Awards (XML + API, max 20 min)")
    from app.services.bosa_award_enrichment import enrich_bosa_can_batch

    total_enriched = 0
    pass_num = 0
    step_start = datetime.now(timezone.utc)
    max_duration_seconds = 20 * 60  # cap at 20 min

    while True:
        elapsed = (datetime.now(timezone.utc) - step_start).total_seconds()
        if elapsed > max_duration_seconds:
            logger.info("  Time cap reached (20 min), stopping.")
            break

        pass_num += 1
        result = enrich_bosa_can_batch(
            db, limit=500, batch_size=50, api_delay_ms=300,
        )
        enriched = result.get("enriched", 0)
        total_enriched += enriched
        logger.info(
            "  Pass %d: enriched=%d (xml=%d, api errors=%d) total=%d [%s]",
            pass_num, enriched,
            result.get("already_has_xml", 0),
            result.get("api_errors", 0),
            total_enriched, _elapsed(step_start),
        )
        if enriched == 0 or result.get("total_eligible", 0) == 0:
            break
        _time.sleep(3)

    return {"total_enriched": total_enriched, "passes": pass_num}


# ═════════════════════════════════════════════════════════════════════
# STEP 6: Merge + cleanup orphan CANs
# ═════════════════════════════════════════════════════════════════════
def step_merge_cleanup(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 6/8: Merge + Cleanup Orphan CANs")
    from app.services.enrichment_service import merge_orphan_cans, cleanup_orphan_cans

    # Merge
    total_merged = 0
    for pass_num in range(1, 11):
        result = merge_orphan_cans(db, limit=5000, dry_run=False)
        merged = result.get("merged", 0)
        total_merged += merged
        logger.info("  Merge pass %d: merged=%d", pass_num, merged)
        if merged == 0 or result.get("total_scanned", 0) < 5000:
            break

    # Cleanup
    dry = cleanup_orphan_cans(db, limit=50000, dry_run=True)
    deleted = 0
    if dry.get("deleted", 0) > 0:
        result = cleanup_orphan_cans(db, limit=50000, dry_run=False)
        deleted = result.get("deleted", 0)
        logger.info("  Cleaned up %d orphan CANs", deleted)
    else:
        logger.info("  No orphan CANs to clean up.")

    return {"merged": total_merged, "cleaned": deleted}


# ═════════════════════════════════════════════════════════════════════
# STEP 7: TED Document Backfill (catalog URLs from raw_data)
# ═════════════════════════════════════════════════════════════════════
def step_ted_doc_backfill(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 7/8: TED Document Backfill (URL cataloging)")
    from app.services.document_extraction import backfill_documents_for_all

    total_created = 0
    total_processed = 0
    dry_streak = 0  # consecutive passes with 0 docs created

    for pass_num in range(1, 51):  # max 50 passes × 2000
        result = backfill_documents_for_all(
            db, source="TED_EU", replace=False, batch_size=10, limit=2000,
        )
        processed = result.get("processed", 0)
        created = result.get("documents_created", 0)
        total_processed += processed
        total_created += created
        logger.info(
            "  Pass %d: +%d notices, +%d docs",
            pass_num, processed, created,
        )
        if processed < 2000:
            logger.info("  Backfill complete (all notices processed).")
            break
        # Early exit: stop if no new docs for 3 consecutive passes
        if created == 0:
            dry_streak += 1
            if dry_streak >= 3:
                logger.info(
                    "  Early exit: 0 docs created for %d consecutive passes (%d notices scanned).",
                    dry_streak, total_processed,
                )
                break
        else:
            dry_streak = 0
        _time.sleep(1)

    return {"processed": total_processed, "created": total_created}


# ═════════════════════════════════════════════════════════════════════
# STEP 8: Watchlist matcher + rescore + email digests
# ═════════════════════════════════════════════════════════════════════
def step_watchlists(db) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 8/8: Watchlist Matcher + Rescore + Email Digests")
    from app.services.watchlist_matcher import run_watchlist_matcher

    results = run_watchlist_matcher(db)
    logger.info(
        "  Matcher: watchlists=%d new_matches=%d emails=%d",
        results.get("watchlists_processed", 0),
        results.get("total_new_matches", 0),
        results.get("emails_sent", 0),
    )

    # Rescore all existing matches
    try:
        from app.models.watchlist_match import WatchlistMatch
        from app.models.watchlist import Watchlist
        from app.models.notice import ProcurementNotice as Notice
        from app.models.user import User
        from app.services.relevance_scoring import calculate_relevance_score

        total_matches = db.query(WatchlistMatch).count()
        if total_matches > 0:
            wl_ids = [r[0] for r in db.query(WatchlistMatch.watchlist_id).distinct().all()]
            watchlists = {wl.id: wl for wl in db.query(Watchlist).filter(Watchlist.id.in_(wl_ids)).all()}
            user_ids = {wl.user_id for wl in watchlists.values() if wl.user_id}
            users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

            updated = 0
            offset = 0
            while offset < total_matches:
                matches = db.query(WatchlistMatch).order_by(WatchlistMatch.id).offset(offset).limit(500).all()
                if not matches:
                    break
                notice_ids = [m.notice_id for m in matches]
                notice_map = {n.id: n for n in db.query(Notice).filter(Notice.id.in_(notice_ids)).all()}
                for match in matches:
                    wl = watchlists.get(match.watchlist_id)
                    notice = notice_map.get(match.notice_id)
                    if wl and notice:
                        user = users.get(wl.user_id) if wl.user_id else None
                        score, explanation = calculate_relevance_score(notice, wl, user=user)
                        match.relevance_score = score
                        match.matched_on = explanation
                        updated += 1
                db.commit()
                offset += 500
            logger.info("  Rescore: updated=%d/%d", updated, total_matches)
        else:
            logger.info("  Rescore: no matches to score.")
    except Exception as e:
        logger.warning("  Rescore error: %s", e)

    return results


# ═════════════════════════════════════════════════════════════════════
# Main entry point
# ═════════════════════════════════════════════════════════════════════
def main() -> int:
    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("ProcureWatch NIGHTLY PIPELINE started at %s", start.isoformat())
    logger.info("Timeout: %ds", TIMEOUT_SECONDS)
    logger.info("=" * 60)

    exit_code = 0

    # Step 1: Migrate
    try:
        step_migrate()
    except Exception as e:
        logger.error(f"Migration failed (non-blocking): {e}")

    # Load models once
    _load_models()

    from app.db.session import SessionLocal
    db = SessionLocal()

    try:
        # Step 2: Import
        try:
            step_import(db)
        except Exception as e:
            logger.error(f"Import failed: {e}")
            exit_code = 1

        # Step 3: Backfill
        try:
            step_backfill(db)
        except Exception as e:
            logger.error(f"Backfill failed: {e}")

        # Step 4: TED CAN enrich
        try:
            step_ted_can_enrich(db)
        except Exception as e:
            logger.error(f"TED CAN enrich failed: {e}")

        # Step 5: BOSA enrich (XML + API)
        try:
            step_bosa_enrich(db)
        except Exception as e:
            logger.error(f"BOSA enrich failed: {e}")

        # Step 6: Merge + cleanup
        try:
            step_merge_cleanup(db)
        except Exception as e:
            logger.error(f"Merge/cleanup failed: {e}")

        # Step 7: TED doc backfill
        try:
            step_ted_doc_backfill(db)
        except Exception as e:
            logger.error(f"TED doc backfill failed: {e}")

        # Step 8: Watchlists + digests (always runs, even if earlier steps failed)
        try:
            step_watchlists(db)
        except Exception as e:
            logger.error(f"Watchlist/digest failed: {e}")
            exit_code = 1

    finally:
        db.close()

    # Cancel timeout
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("=" * 60)
    logger.info(
        "NIGHTLY PIPELINE COMPLETE in %s (exit=%d)",
        _elapsed(start), exit_code,
    )
    logger.info("=" * 60)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
