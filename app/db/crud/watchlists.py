"""CRUD operations for watchlists and watchlist notice matching."""
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.models.watchlist import Watchlist


def create_watchlist(
    db: Session,
    name: str,
    is_enabled: bool = True,
    term: Optional[str] = None,
    cpv_prefix: Optional[str] = None,
    buyer_contains: Optional[str] = None,
    procedure_type: Optional[str] = None,
    country: str = "BE",
    language: Optional[str] = None,
    notify_email: Optional[str] = None,
) -> Watchlist:
    """Create a new watchlist."""
    wl = Watchlist(
        name=name,
        is_enabled=is_enabled,
        term=term,
        cpv_prefix=cpv_prefix,
        buyer_contains=buyer_contains,
        procedure_type=procedure_type,
        country=country,
        language=language,
        notify_email=notify_email,
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def get_watchlist_by_id(db: Session, watchlist_id: str) -> Optional[Watchlist]:
    """Get a watchlist by ID."""
    return db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()


def list_watchlists(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[Watchlist], int]:
    """List watchlists with pagination. Returns (watchlists, total_count)."""
    query = db.query(Watchlist)
    total = query.count()
    items = query.order_by(Watchlist.updated_at.desc()).offset(offset).limit(limit).all()
    return items, total


def list_watchlists_for_refresh(
    db: Session,
    watchlist_id: Optional[str] = None,
) -> list[Watchlist]:
    """Return watchlists to refresh: one by id if given, else all enabled."""
    if watchlist_id:
        wl = get_watchlist_by_id(db, watchlist_id)
        return [wl] if wl else []
    return db.query(Watchlist).filter(Watchlist.is_enabled == True).all()


def update_watchlist(
    db: Session,
    watchlist_id: str,
    **kwargs: object,
) -> Optional[Watchlist]:
    """Update a watchlist by ID (partial update)."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        return None
    for key, value in kwargs.items():
        if hasattr(wl, key):
            setattr(wl, key, value)
    db.commit()
    db.refresh(wl)
    return wl


def delete_watchlist(db: Session, watchlist_id: str) -> bool:
    """Delete a watchlist by ID (hard delete)."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        return False
    db.delete(wl)
    db.commit()
    return True


def list_notices_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[Notice], int]:
    """
    List notices that match the watchlist filters.
    Matching: all non-null filters must match.
    - term: case-insensitive contains on title
    - cpv_prefix: main cpv or any additional cpv startswith prefix (normalized)
    - buyer_contains: case-insensitive contains on buyer_name (skip if buyer_name null)
    - procedure_type: exact match
    - country: exact match
    - language: exact match if set on notice
    Sort: published_at desc nulls_last, then updated_at desc.
    Returns (notices, total_count).
    """
    query = db.query(Notice)

    if watchlist.term:
        query = query.filter(Notice.title.ilike(f"%{watchlist.term}%"))

    if watchlist.cpv_prefix:
        cpv_clean = watchlist.cpv_prefix.replace("-", "").strip()
        if cpv_clean:
            query = query.outerjoin(
                NoticeCpvAdditional,
                Notice.id == NoticeCpvAdditional.notice_id,
            ).filter(
                or_(
                    Notice.cpv_main_code.like(f"{cpv_clean}%"),
                    Notice.cpv.like(f"{cpv_clean}%"),
                    NoticeCpvAdditional.cpv_code.like(f"{cpv_clean}%"),
                )
            ).distinct()

    if watchlist.buyer_contains:
        query = query.filter(Notice.buyer_name.isnot(None)).filter(
            Notice.buyer_name.ilike(f"%{watchlist.buyer_contains}%")
        )

    if watchlist.procedure_type:
        query = query.filter(Notice.procedure_type == watchlist.procedure_type)

    if watchlist.country:
        query = query.filter(Notice.country == watchlist.country.upper())

    if watchlist.language:
        query = query.filter(Notice.language == watchlist.language)

    total = query.count()
    query = query.order_by(
        Notice.published_at.desc().nulls_last(),
        Notice.updated_at.desc(),
    )
    notices = query.offset(offset).limit(limit).all()
    return notices, total


def get_new_since_cutoff(watchlist: Watchlist) -> Optional[datetime]:
    """Cutoff for 'new since last run': last_notified_at else last_refresh_at. None = first run."""
    return watchlist.last_notified_at or watchlist.last_refresh_at


def _apply_watchlist_filters(query, watchlist: Watchlist):
    """Apply watchlist filters to a Notice query (term, cpv_prefix, buyer, procedure_type, country, language)."""
    if watchlist.term:
        query = query.filter(Notice.title.ilike(f"%{watchlist.term}%"))
    if watchlist.cpv_prefix:
        cpv_clean = watchlist.cpv_prefix.replace("-", "").strip()
        if cpv_clean:
            query = query.outerjoin(
                NoticeCpvAdditional,
                Notice.id == NoticeCpvAdditional.notice_id,
            ).filter(
                or_(
                    Notice.cpv_main_code.like(f"{cpv_clean}%"),
                    Notice.cpv.like(f"{cpv_clean}%"),
                    NoticeCpvAdditional.cpv_code.like(f"{cpv_clean}%"),
                )
            ).distinct()
    if watchlist.buyer_contains:
        query = query.filter(Notice.buyer_name.isnot(None)).filter(
            Notice.buyer_name.ilike(f"%{watchlist.buyer_contains}%")
        )
    if watchlist.procedure_type:
        query = query.filter(Notice.procedure_type == watchlist.procedure_type)
    if watchlist.country:
        query = query.filter(Notice.country == watchlist.country.upper())
    if watchlist.language:
        query = query.filter(Notice.language == watchlist.language)
    return query


def _seen_after_criterion(cutoff: datetime):
    """New since cutoff: first_seen_at > cutoff (preferred) or created_at > cutoff if first_seen_at null."""
    return or_(
        Notice.first_seen_at > cutoff,
        and_(Notice.first_seen_at.is_(None), Notice.created_at > cutoff),
    )


def list_new_notices_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    seen_after: datetime,
    limit: int = 30,
) -> list[Notice]:
    """
    Notices matching watchlist and newly seen by ProcureWatch since seen_after.
    Uses first_seen_at (preferred) or created_at if first_seen_at null.
    Sort: published_at desc nulls_last, updated_at desc. Returns at most limit items.
    """
    query = _apply_watchlist_filters(db.query(Notice), watchlist)
    query = query.filter(_seen_after_criterion(seen_after))
    query = query.order_by(
        Notice.published_at.desc().nulls_last(),
        Notice.updated_at.desc(),
    )
    return query.limit(limit).all()


def count_new_notices_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    seen_after: datetime,
) -> int:
    """Count notices matching watchlist and newly seen since seen_after (first_seen_at or created_at)."""
    query = _apply_watchlist_filters(db.query(Notice), watchlist)
    query = query.filter(_seen_after_criterion(seen_after))
    return query.count()


def list_new_since_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[Notice], int]:
    """
    Notices matching watchlist and newly seen since last_notified_at (fallback last_refresh_at).
    If no cutoff (first run), returns ([], 0). Same ordering as preview.
    Returns (notices, total_count).
    """
    cutoff = get_new_since_cutoff(watchlist)
    if cutoff is None:
        return [], 0
    query = _apply_watchlist_filters(db.query(Notice), watchlist)
    query = query.filter(_seen_after_criterion(cutoff))
    total = query.count()
    query = query.order_by(
        Notice.published_at.desc().nulls_last(),
        Notice.updated_at.desc(),
    )
    notices = query.offset(offset).limit(limit).all()
    return notices, total
