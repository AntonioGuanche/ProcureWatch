"""Watchlist (alerts) endpoints: CRUD + preview matches + refresh."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas.notice import NoticeListResponse, NoticeRead
from app.api.schemas.watchlist import (
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistRead,
    WatchlistUpdate,
)
from app.db.crud.watchlists import (
    create_watchlist,
    delete_watchlist,
    get_watchlist_by_id,
    list_new_since_for_watchlist,
    list_notices_for_watchlist,
    list_watchlists,
    update_watchlist,
)
from app.db.session import get_db

router = APIRouter(prefix="/watchlists", tags=["watchlists"])

# Rate limit: manual refresh only if last_refresh_at is older than this (seconds)
REFRESH_RATE_LIMIT_SECONDS = 600  # 10 minutes


@router.post("", response_model=WatchlistRead, status_code=201)
async def post_watchlist(
    body: WatchlistCreate,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Create a new watchlist."""
    wl = create_watchlist(
        db,
        name=body.name,
        is_enabled=body.is_enabled,
        term=body.term,
        cpv_prefix=body.cpv_prefix,
        buyer_contains=body.buyer_contains,
        procedure_type=body.procedure_type,
        country=body.country,
        language=body.language,
        notify_email=body.notify_email,
    )
    return wl


@router.get("", response_model=WatchlistListResponse)
async def get_watchlists(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> WatchlistListResponse:
    """List watchlists with pagination."""
    offset = (page - 1) * page_size
    items, total = list_watchlists(db, limit=page_size, offset=offset)
    return WatchlistListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{watchlist_id}/preview", response_model=NoticeListResponse)
async def get_watchlist_preview(
    watchlist_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """
    Preview notices that match this watchlist's filters.
    Same shape as GET /api/notices: total, page, page_size, items.
    Sort: newest published_at desc, then updated_at desc.
    """
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    offset = (page - 1) * page_size
    notices, total = list_notices_for_watchlist(db, wl, limit=page_size, offset=offset)
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=notices,
    )


@router.get("/{watchlist_id}/new", response_model=NoticeListResponse)
async def get_watchlist_new(
    watchlist_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """
    Notices matching this watchlist that are new since last_notified_at (fallback last_refresh_at).
    Uses first_seen_at (preferred) or created_at if first_seen_at null. If no cutoff (first run), returns empty.
    Same shape as preview: total, page, page_size, items. Sort: published_at desc, updated_at desc.
    """
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    offset = (page - 1) * page_size
    notices, total = list_new_since_for_watchlist(db, wl, limit=page_size, offset=offset)
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=notices,
    )


@router.get("/{watchlist_id}", response_model=WatchlistRead)
async def get_watchlist(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Get a watchlist by ID."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return wl


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def patch_watchlist(
    watchlist_id: str,
    body: WatchlistUpdate,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Update a watchlist (partial)."""
    payload = body.model_dump(exclude_unset=True)
    wl = update_watchlist(db, watchlist_id, **payload)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return wl


@router.post("/{watchlist_id}/refresh")
async def post_watchlist_refresh(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Run refresh for this watchlist (max_pages=3, early-stop). Sends email digest if
    notify_email set and not first run and new notices > 0. Returns JSON summary.
    Rate limited: 429 if last_refresh_at < 10 minutes ago.
    """
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    now = datetime.now(timezone.utc)
    if wl.last_refresh_at:
        # Compare naive and aware: make last_refresh_at aware if needed
        last = wl.last_refresh_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < REFRESH_RATE_LIMIT_SECONDS:
            raise HTTPException(
                status_code=429,
                detail="Refresh rate limited: wait at least 10 minutes between manual refreshes",
            )
    from ingest.refresh_watchlists import refresh_one_watchlist
    summary = refresh_one_watchlist(db, wl, max_pages=3, page_size=25)
    return summary


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist_route(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a watchlist (hard delete)."""
    if not delete_watchlist(db, watchlist_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
