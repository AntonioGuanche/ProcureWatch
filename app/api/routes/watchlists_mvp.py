"""Watchlist MVP endpoints: create, list, refresh, matches (multi-tenant)."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import rate_limit_public
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.services.subscription import check_watchlist_limit, get_plan_limits, effective_plan
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
from app.models.user import User

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
    current_user: User = Depends(get_current_user),
) -> WatchlistListResponse:
    """List watchlists for the current user."""
    offset = (page - 1) * page_size
    items, total = list_watchlists(db, limit=page_size, offset=offset, user_id=current_user.id)
    return WatchlistListResponse(
        total=total, page=page, page_size=page_size,
        items=[_to_read(wl) for wl in items],
    )


@router.post("", response_model=WatchlistRead, status_code=201)
async def post_watchlist(
    body: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistRead:
    """Create a new watchlist for the current user."""
    # Check plan limits
    limit_error = check_watchlist_limit(db, current_user)
    if limit_error:
        raise HTTPException(status_code=403, detail=limit_error)
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
        user_id=current_user.id,
    )
    return _to_read(wl)


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def patch_watchlist(
    watchlist_id: str,
    body: WatchlistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistRead:
    """Partial update of a watchlist (owner only)."""
    # Check ownership
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    update_data = body.model_dump(exclude_unset=True)
    wl = update_watchlist(db, watchlist_id, **update_data)
    return _to_read(wl)


@router.delete("/{watchlist_id}", status_code=204)
async def del_watchlist(
    watchlist_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a watchlist (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    if not delete_watchlist(db, watchlist_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")


@router.get("/{watchlist_id}", response_model=WatchlistRead)
async def get_watchlist_endpoint(
    watchlist_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistRead:
    """Get a single watchlist by ID (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _to_read(wl)


@router.post("/{watchlist_id}/refresh")
async def post_watchlist_refresh(
    watchlist_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Recompute matches for this watchlist (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    summary = refresh_watchlist_matches(db, wl, user=current_user)
    return summary


@router.get("/{watchlist_id}/matches", response_model=WatchlistMatchesResponse)
async def get_watchlist_matches(
    watchlist_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistMatchesResponse:
    """Get stored matches for this watchlist (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    
    # Enforce plan result limits
    plan = effective_plan(current_user)
    limits = get_plan_limits(plan)
    max_results = limits.max_results_per_watchlist
    if max_results != -1:
        page_size = min(page_size, max_results)
        if (page - 1) * page_size >= max_results:
            return WatchlistMatchesResponse(total=max_results, page=page, page_size=page_size, items=[])

    offset = (page - 1) * page_size
    results, total = list_watchlist_matches(db, watchlist_id, limit=page_size, offset=offset)
    
    items = []
    for notice, matched_on, relevance_score in results:
        items.append(
            WatchlistMatchRead(
                notice=NoticeRead.model_validate(notice),
                matched_on=matched_on,
                relevance_score=relevance_score,
            )
        )
    
    return WatchlistMatchesResponse(total=min(total, max_results) if max_results != -1 else total, page=page, page_size=page_size, items=items)


@router.get("/{watchlist_id}/preview", response_model=NoticeListResponse)
async def get_watchlist_preview(
    watchlist_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    source: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("date_desc"),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoticeListResponse:
    """Preview all notices matching this watchlist's filters (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Enforce plan result limits
    plan = effective_plan(current_user)
    limits = get_plan_limits(plan)
    max_results = limits.max_results_per_watchlist
    if max_results != -1:
        page_size = min(page_size, max_results)
        if (page - 1) * page_size >= max_results:
            return NoticeListResponse(total=max_results, page=page, page_size=page_size, items=[])

    offset = (page - 1) * page_size
    notices, total = list_notices_for_watchlist(
        db, wl, limit=page_size, offset=offset,
        source=source, q=q, sort=sort, active_only=active_only,
    )
    capped_total = min(total, max_results) if max_results != -1 else total
    return NoticeListResponse(
        total=capped_total,
        page=page,
        page_size=page_size,
        items=[NoticeRead.model_validate(n) for n in notices],
    )


@router.get("/{watchlist_id}/new", response_model=NoticeListResponse)
async def get_watchlist_new(
    watchlist_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    source: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("date_desc"),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoticeListResponse:
    """Get notices matching this watchlist that were created since the last refresh (owner only)."""
    wl = get_watchlist_by_id(db, watchlist_id, user_id=current_user.id)
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Enforce plan result limits
    plan = effective_plan(current_user)
    limits = get_plan_limits(plan)
    max_results = limits.max_results_per_watchlist
    if max_results != -1:
        page_size = min(page_size, max_results)
        if (page - 1) * page_size >= max_results:
            return NoticeListResponse(total=max_results, page=page, page_size=page_size, items=[])

    offset = (page - 1) * page_size
    notices, total = list_new_since_for_watchlist(
        db, wl, limit=page_size, offset=offset,
        source=source, q=q, sort=sort, active_only=active_only,
    )
    capped_total = min(total, max_results) if max_results != -1 else total
    return NoticeListResponse(
        total=capped_total,
        page=page,
        page_size=page_size,
        items=[NoticeRead.model_validate(n) for n in notices],
    )
