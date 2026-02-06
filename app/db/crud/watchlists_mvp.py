"""CRUD operations for watchlists MVP: arrays, match storage, description matching."""
import json
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.models.notice_detail import NoticeDetail
from app.db.models.watchlist import Watchlist
from app.db.models.watchlist_match import WatchlistMatch
from app.utils.searchable_text import build_searchable_text
from app.utils.sources import DEFAULT_SOURCES, get_notice_sources_for_watchlist


def _parse_array(value: Optional[str]) -> list[str]:
    """Parse comma-separated string to list, empty if None."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _join_array(items: list[str]) -> Optional[str]:
    """Join list to comma-separated string, None if empty."""
    if not items:
        return None
    return ",".join(item.strip() for item in items if item.strip())


def _parse_sources_json(value: Optional[str]) -> list[str]:
    """Parse JSON array string to list, default to both sources if None/empty."""
    if not value:
        return list(DEFAULT_SOURCES)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(s).strip() for s in parsed if str(s).strip()]
        return list(DEFAULT_SOURCES)
    except (json.JSONDecodeError, TypeError):
        return list(DEFAULT_SOURCES)


def _join_sources_json(sources: list[str] | None) -> Optional[str]:
    """Join sources list to JSON string, default to both if None/empty."""
    if not sources:
        return json.dumps(DEFAULT_SOURCES)
    return json.dumps([s.strip() for s in sources if s.strip()])


def create_watchlist(
    db: Session,
    name: str,
    keywords: list[str] | None = None,
    countries: list[str] | None = None,
    cpv_prefixes: list[str] | None = None,
    sources: list[str] | None = None,
) -> Watchlist:
    """Create a new watchlist with arrays."""
    wl = Watchlist(
        name=name,
        keywords=_join_array(keywords or []),
        countries=_join_array(countries or []),
        cpv_prefixes=_join_array(cpv_prefixes or []),
        sources=_join_sources_json(sources),
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


def update_watchlist(
    db: Session,
    watchlist_id: str,
    name: Optional[str] = None,
    keywords: Optional[list[str]] = None,
    countries: Optional[list[str]] = None,
    cpv_prefixes: Optional[list[str]] = None,
    sources: Optional[list[str]] = None,
) -> Optional[Watchlist]:
    """Update a watchlist by ID (partial update)."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        return None
    if name is not None:
        wl.name = name
    if keywords is not None:
        wl.keywords = _join_array(keywords)
    if countries is not None:
        wl.countries = _join_array(countries)
    if cpv_prefixes is not None:
        wl.cpv_prefixes = _join_array(cpv_prefixes)
    if sources is not None:
        wl.sources = _join_sources_json(sources)
    db.commit()
    db.refresh(wl)
    return wl


def delete_watchlist(db: Session, watchlist_id: str) -> bool:
    """Delete a watchlist by ID (hard delete, cascades to matches)."""
    wl = get_watchlist_by_id(db, watchlist_id)
    if not wl:
        return False
    db.delete(wl)
    db.commit()
    return True


def _match_keywords_sql(query, keywords: list[str]) -> Tuple[Any, list[str]]:
    """
    Add SQL filters for keyword matching (title OR description from notice_detail or raw_json).
    Returns (modified_query, matched_keywords_list_for_explanation).
    Note: This is a simplified version - full description matching requires JSON extraction which is complex in SQL.
    For MVP, we match on title primarily, with raw_json fallback handled in Python for matched notices.
    """
    if not keywords:
        return query, []
    
    # Build OR conditions for each keyword in title (case-insensitive)
    keyword_conditions = []
    for keyword in keywords:
        keyword_conditions.append(Notice.title.ilike(f"%{keyword}%"))
    
    if keyword_conditions:
        query = query.filter(or_(*keyword_conditions))
    
    return query, keywords


def _match_countries_sql(query, countries: list[str]) -> Tuple[Any, Optional[str]]:
    """Add SQL filter for country matching. Returns (modified_query, matched_country_for_explanation)."""
    if not countries:
        return query, None
    query = query.filter(Notice.country.in_([c.upper() for c in countries]))
    return query, countries[0] if countries else None


def _match_cpv_prefixes_sql(query, cpv_prefixes: list[str]) -> Tuple[Any, list[str]]:
    """
    Add SQL filters for CPV prefix matching (main or additional).
    Returns (modified_query, matched_prefixes_for_explanation).
    """
    if not cpv_prefixes:
        return query, []
    
    # Build conditions for each prefix
    cpv_conditions = []
    for prefix in cpv_prefixes:
        prefix_clean = prefix.replace("-", "").strip()
        if not prefix_clean:
            continue
        # Match main CPV (normalized, no hyphens)
        cpv_conditions.append(
            func.replace(func.replace(Notice.cpv_main_code, "-", ""), " ", "").like(f"{prefix_clean}%")
        )
        cpv_conditions.append(
            func.replace(func.replace(Notice.cpv, "-", ""), " ", "").like(f"{prefix_clean}%")
        )
    
    if cpv_conditions:
        # Also check additional CPVs via join
        query = query.outerjoin(
            NoticeCpvAdditional,
            Notice.id == NoticeCpvAdditional.notice_id,
        )
        additional_conditions = []
        for prefix in cpv_prefixes:
            prefix_clean = prefix.replace("-", "").strip()
            if prefix_clean:
                additional_conditions.append(
                    func.replace(func.replace(NoticeCpvAdditional.cpv_code, "-", ""), " ", "").like(f"{prefix_clean}%")
                )
        if additional_conditions:
            cpv_conditions.extend(additional_conditions)
        query = query.filter(or_(*cpv_conditions)).distinct()
    
    return query, cpv_prefixes


def _match_sources_sql(query, sources: list[str]) -> Any:
    """
    Add SQL filter for source matching.
    Converts watchlist source identifiers (TED, BOSA) to notice.source values.
    """
    if not sources:
        # If empty, default to both (should not happen due to validation, but safe fallback)
        notice_sources = get_notice_sources_for_watchlist(DEFAULT_SOURCES)
    else:
        notice_sources = get_notice_sources_for_watchlist(sources)
    
    if notice_sources:
        query = query.filter(Notice.source.in_(notice_sources))
    
    return query


def _build_matched_on_explanation(
    matched_keywords: list[str],
    matched_country: Optional[str],
    matched_cpv_prefixes: list[str],
) -> str:
    """Build human-readable explanation of why notice matched."""
    parts = []
    if matched_keywords:
        parts.append(f"keywords: {', '.join(matched_keywords)}")
    if matched_country:
        parts.append(f"country: {matched_country}")
    if matched_cpv_prefixes:
        parts.append(f"CPV: {', '.join(matched_cpv_prefixes)}")
    return ", ".join(parts) if parts else "no filters"


def _check_keyword_in_searchable_text(notice: Notice, keywords: list[str], db: Session) -> list[str]:
    """
    Check if keywords appear in searchable text (title + raw_json + notice_detail).
    Returns list of matched keywords.
    Uses build_searchable_text for comprehensive matching.
    """
    if not keywords:
        return []
    
    # Get notice_detail if available
    detail = db.query(NoticeDetail).filter(NoticeDetail.notice_id == notice.id).first()
    
    # Build searchable text
    searchable_text = build_searchable_text(notice, detail)
    
    matched = []
    searchable_lower = searchable_text.lower()
    for keyword in keywords:
        if keyword.lower() in searchable_lower:
            matched.append(keyword)
    
    return matched


def refresh_watchlist_matches(db: Session, watchlist: Watchlist) -> dict[str, int]:
    """
    Recompute and store matches for a watchlist idempotently using SQL where possible.
    Deletes existing matches, then recomputes and stores new ones.
    Returns dict with counts: matched, added.
    """
    keywords = _parse_array(watchlist.keywords)
    countries = _parse_array(watchlist.countries)
    cpv_prefixes = _parse_array(watchlist.cpv_prefixes)
    sources = _parse_sources_json(watchlist.sources)
    
    # Delete existing matches (idempotent: clear old matches)
    db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == watchlist.id).delete()
    
    # Build SQL query with filters applied
    query = db.query(Notice)
    
    # Apply source filter first (most restrictive)
    query = _match_sources_sql(query, sources)
    
    # Apply keyword filter (title match in SQL)
    query, matched_keywords_for_explanation = _match_keywords_sql(query, keywords)
    
    # Apply country filter
    query, matched_country_for_explanation = _match_countries_sql(query, countries)
    
    # Apply CPV prefix filter
    query, matched_cpv_prefixes_for_explanation = _match_cpv_prefixes_sql(query, cpv_prefixes)
    
    # Execute query to get candidate notices
    candidate_notices = query.all()
    matched_count = 0
    
    # For each candidate, verify keyword match using searchable text, and build explanation
    for notice in candidate_notices:
        # If keywords provided, check if ALL keywords match in searchable text (AND logic)
        matched_keywords = []
        if keywords:
            # Use searchable text for comprehensive matching
            matched_keywords = _check_keyword_in_searchable_text(notice, keywords, db)
            
            # Require ALL keywords to match (AND logic)
            if len(matched_keywords) < len(keywords):
                continue  # Not all keywords matched
        
        # Determine which CPV prefix matched (if any)
        matched_cpv = []
        if cpv_prefixes:
            main_cpv = (notice.cpv_main_code or notice.cpv or "").replace("-", "").strip()
            for prefix in cpv_prefixes:
                prefix_clean = prefix.replace("-", "").strip()
                if prefix_clean and main_cpv.startswith(prefix_clean):
                    matched_cpv.append(prefix)
                    continue
                # Check additional CPVs
                additional = db.query(NoticeCpvAdditional).filter(
                    NoticeCpvAdditional.notice_id == notice.id
                ).all()
                for add_cpv in additional:
                    if add_cpv.cpv_code and add_cpv.cpv_code.replace("-", "").startswith(prefix_clean):
                        matched_cpv.append(prefix)
                        break
        
        # Build explanation
        matched_on = _build_matched_on_explanation(
            matched_keywords if keywords else [],
            matched_country_for_explanation,
            matched_cpv if cpv_prefixes else [],
        )
        
        # Create match record
        match = WatchlistMatch(
            watchlist_id=watchlist.id,
            notice_id=notice.id,
            matched_on=matched_on,
        )
        db.add(match)
        matched_count += 1
    
    # Update watchlist last_refresh_at
    watchlist.last_refresh_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"matched": matched_count, "added": matched_count}


def list_watchlist_matches(
    db: Session,
    watchlist_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[Tuple[Notice, str]], int]:
    """
    List stored matches for a watchlist with matched_on explanations.
    Returns ((notice, matched_on), total_count).
    """
    query = (
        db.query(Notice, WatchlistMatch.matched_on)
        .join(WatchlistMatch, Notice.id == WatchlistMatch.notice_id)
        .filter(WatchlistMatch.watchlist_id == watchlist_id)
    )
    total = query.count()
    results = (
        query.order_by(Notice.published_at.desc().nulls_last(), Notice.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return results, total
