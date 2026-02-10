"""Watchlist MVP endpoints: create, list, refresh, matches."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import rate_limit_public
from sqlalchemy.orm import Session

from app.api.schemas.notice import NoticeRead, NoticeListResponse
from app.api.schemas.watchlist import (
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistMatchesResponse,
    WatchlistMatchRead,
    WatchlistRead,
    WatchlistUpdate,
)
from app.db.crud.watchlists_mvp import (
    create_watchlist,
    delete_watchlist,
    get_watchlist_by_id,
    list_watchlist_matches,
    list_watchlists,
    list_notices_for_watchlist,
    list_new_since_for_watchlist,
    refresh_watchlist_matches,
    update_watchlist,
    _parse_array,
    _parse_sources_json,
)
from app.db.session import get_db

router = APIRouter(prefix="/watchlists", tags=["watchlists"], dependencies=[Depends(rate_limit_public)])


def _to_read(wl) -> WatchlistRead:
    """Convert Watchlist ORM to WatchlistRead schema."""
    return WatchlistRead(
        id=wl.id,
        name=wl.name,
        keywords=_parse_array(wl.keywords),
        countries=_parse_array(wl.countries),
        cpv_prefixes=_parse_array(wl.cpv_prefixes),
        nuts_prefixes=_parse_array(getattr(wl, "nuts_prefixes", None)),
        sources=_parse_sources_json(wl.sources),
        enabled=getattr(wl, "enabled", True),
        notify_email=getattr(wl, "notify_email", None),
        last_refresh_at=wl.last_refresh_at,
        created_at=wl.created_at,
        updated_at=wl.updated_at,
    )


@router.get("", response_model=WatchlistListResponse)
async def get_watchlists(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> WatchlistListResponse:
    """List watchlists with pagination."""
    offset = (page - 1) * page_size
    items, total = list_watchlists(db, limit=page_size, offset=offset)
    return WatchlistListResponse(
        total=total, page=page, page_size=page_size,
        items=[_to_read(wl) for wl in items],
    )


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
        nuts_prefixes=body.nuts_prefixes,
        sources=body.sources,
        enabled=body.enabled,
        notify_email=body.notify_email,
    )
    return _to_read(wl)


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def patch_watchlist(
    watchlist_id: str,
    body: WatchlistUpdate,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Partial update of a watchlist."""
    update_data = body.model_dump(exclude_unset=True)
    wl = update_watchlist(db, watchlist_id, **update_data)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _to_read(wl)


@router.delete("/{watchlist_id}", status_code=204)
async def del_watchlist(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a watchlist and its matches."""
    if not delete_watchlist(db, watchlist_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")


@router.get("/{watchlist_id}", response_model=WatchlistRead)
async def get_watchlist_endpoint(
    watchlist_id: str,
    db: Session = Depends(get_db),
) -> WatchlistRead:
    """Get a single watchlist by ID."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _to_read(wl)


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


@router.get("/{watchlist_id}/preview", response_model=NoticeListResponse)
async def get_watchlist_preview(
    watchlist_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """Preview all notices matching this watchlist's filters."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    offset = (page - 1) * page_size
    notices, total = list_notices_for_watchlist(db, wl, limit=page_size, offset=offset)
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[NoticeRead.model_validate(n) for n in notices],
    )


@router.get("/{watchlist_id}/new", response_model=NoticeListResponse)
async def get_watchlist_new(
    watchlist_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """Get notices matching this watchlist that were created since the last refresh."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    offset = (page - 1) * page_size
    notices, total = list_new_since_for_watchlist(db, wl, limit=page_size, offset=offset)
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[NoticeRead.model_validate(n) for n in notices],
    )
