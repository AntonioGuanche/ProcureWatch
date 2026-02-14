"""Watchlist matching, rescoring, backfill, data-quality, duplicates, test-email, merge/cleanup."""
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_admin_key, rate_limit_admin
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["enrichment"],
    dependencies=[Depends(require_admin_key), Depends(rate_limit_admin)],
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


