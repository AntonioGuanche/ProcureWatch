"""Watchlist MVP endpoints: create, list, refresh, matches."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas.notice import NoticeRead
from app.api.schemas.watchlist import (
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistMatchesResponse,
    WatchlistMatchRead,
    WatchlistRead,
)
from app.db.crud.watchlists_mvp import (
    create_watchlist,
    delete_watchlist,
    get_watchlist_by_id,
    list_watchlist_matches,
    list_watchlists,
    refresh_watchlist_matches,
    update_watchlist,
    _parse_array,
    _parse_sources_json,
)
from app.db.session import get_db

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=WatchlistListResponse)
async def get_watchlists(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> WatchlistListResponse:
    """List watchlists with pagination."""
    offset = (page - 1) * page_size
    items, total = list_watchlists(db, limit=page_size, offset=offset)
    # Convert to response format (parse arrays from comma-separated strings and JSON)
    watchlist_reads = []
    for wl in items:
        watchlist_reads.append(
            WatchlistRead(
                id=wl.id,
                name=wl.name,
                keywords=_parse_array(wl.keywords),
                countries=_parse_array(wl.countries),
                cpv_prefixes=_parse_array(wl.cpv_prefixes),
                sources=_parse_sources_json(wl.sources),
                last_refresh_at=wl.last_refresh_at,
                created_at=wl.created_at,
                updated_at=wl.updated_at,
            )
        )
    return WatchlistListResponse(total=total, page=page, page_size=page_size, items=watchlist_reads)


@router.post("", response_model=WatchlistRead, status_code=201)
async def post_watchlist(
    body: WatchlistCreate,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Create a new watchlist."""
    wl = create_watchlist(
        db,
        name=body.name,
        keywords=body.keywords,
        countries=body.countries,
        cpv_prefixes=body.cpv_prefixes,
        sources=body.sources,
    )
    return WatchlistRead(
        id=wl.id,
        name=wl.name,
        keywords=_parse_array(wl.keywords),
        countries=_parse_array(wl.countries),
        cpv_prefixes=_parse_array(wl.cpv_prefixes),
        sources=_parse_sources_json(wl.sources),
        last_refresh_at=wl.last_refresh_at,
        created_at=wl.created_at,
        updated_at=wl.updated_at,
    )


@router.post("/{watchlist_id}/refresh")
async def post_watchlist_refresh(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Recompute matches for this watchlist idempotently.
    Deletes existing matches, then recomputes and stores new ones.
    Returns summary with matched count.
    """
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    summary = refresh_watchlist_matches(db, wl)
    return summary


@router.get("/{watchlist_id}/matches", response_model=WatchlistMatchesResponse)
async def get_watchlist_matches(
    watchlist_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> WatchlistMatchesResponse:
    """
    Get stored matches for this watchlist with matched_on explanations.
    Returns paginated list of matched notices.
    """
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    offset = (page - 1) * page_size
    results, total = list_watchlist_matches(db, watchlist_id, limit=page_size, offset=offset)
    
    items = []
    for notice, matched_on in results:
        items.append(
            WatchlistMatchRead(
                notice=NoticeRead.model_validate(notice),
                matched_on=matched_on,
            )
        )
    
    return WatchlistMatchesResponse(total=total, page=page, page_size=page_size, items=items)
