"""Admin endpoints for email digest testing and manual trigger."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.watchlist import Watchlist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/digest", tags=["admin"])


@router.post("/test")
async def send_test_digest(
    watchlist_id: str = Query(..., description="Watchlist ID to test"),
    to_email: str = Query(None, description="Override recipient email (defaults to watchlist notify_email)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Send a test digest email for a specific watchlist.
    Uses the last 10 matches or finds fresh matches if none exist.
    Admin only.
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Admin only")

    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not wl:
        raise HTTPException(404, "Watchlist not found")

    # Find recent matches
    from app.models.watchlist_match import WatchlistMatch
    from app.models.notice import ProcurementNotice as Notice

    matches = (
        db.query(Notice)
        .join(WatchlistMatch, WatchlistMatch.notice_id == Notice.id)
        .filter(WatchlistMatch.watchlist_id == wl.id)
        .order_by(Notice.publication_date.desc().nullslast())
        .limit(10)
        .all()
    )

    if not matches:
        # Try fresh match
        from app.services.watchlist_matcher import match_watchlist
        matches = match_watchlist(db, wl)[:10]

    if not matches:
        return {"status": "no_matches", "message": "No matching notices found for this watchlist"}

    # Convert to email dicts
    from app.services.watchlist_matcher import _notice_to_email_dict
    email_data = [_notice_to_email_dict(n) for n in matches]

    # Send
    from app.services.notification_service import send_watchlist_notification
    recipient = to_email or wl.notify_email or current_user.email

    try:
        send_watchlist_notification(wl, email_data, to_address=recipient)
        return {
            "status": "sent",
            "to": recipient,
            "matches": len(email_data),
            "watchlist": wl.name,
        }
    except Exception as e:
        logger.error(f"Test digest failed: {e}")
        raise HTTPException(500, f"Email send failed: {e}")


@router.post("/preview")
async def preview_digest_html(
    watchlist_id: str = Query(..., description="Watchlist ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the HTML of a digest email for preview (no actual send)."""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin only")

    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not wl:
        raise HTTPException(404, "Watchlist not found")

    from app.models.watchlist_match import WatchlistMatch
    from app.models.notice import ProcurementNotice as Notice

    matches = (
        db.query(Notice)
        .join(WatchlistMatch, WatchlistMatch.notice_id == Notice.id)
        .filter(WatchlistMatch.watchlist_id == wl.id)
        .order_by(Notice.publication_date.desc().nullslast())
        .limit(10)
        .all()
    )

    from app.services.watchlist_matcher import _notice_to_email_dict
    from app.services.email_templates import build_digest_html

    email_data = [_notice_to_email_dict(n) for n in matches]
    html_body = build_digest_html(wl.name, email_data)

    return {
        "watchlist": wl.name,
        "matches": len(email_data),
        "html": html_body,
    }


@router.post("/run-all")
async def run_all_digests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually trigger watchlist matching + email digests for all enabled watchlists."""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin only")

    from app.services.watchlist_matcher import run_watchlist_matcher
    results = run_watchlist_matcher(db)
    return results
