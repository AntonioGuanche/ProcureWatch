"""CRUD operations for watchlists MVP: arrays, match storage, description matching."""
import json
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import and_, cast, or_, func, String
from sqlalchemy.orm import Session

from app.models.notice import Notice  # alias for ProcurementNotice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.models.notice_detail import NoticeDetail
from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch
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
    nuts_prefixes: list[str] | None = None,
    sources: list[str] | None = None,
    enabled: bool = True,
    notify_email: str | None = None,
    user_id: str | None = None,
) -> Watchlist:
    """Create a new watchlist with arrays."""
    wl = Watchlist(
        name=name,
        keywords=_join_array(keywords or []),
        countries=_join_array(countries or []),
        cpv_prefixes=_join_array(cpv_prefixes or []),
        nuts_prefixes=_join_array(nuts_prefixes or []),
        sources=_join_sources_json(sources),
        enabled=enabled,
        notify_email=notify_email,
        user_id=user_id,
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def get_watchlist_by_id(db: Session, watchlist_id: str, user_id: str | None = None) -> Optional[Watchlist]:
    """Get a watchlist by ID."""
    query = db.query(Watchlist).filter(Watchlist.id == watchlist_id)
    if user_id:
        query = query.filter(Watchlist.user_id == user_id)
    return query.first()


def list_watchlists(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    user_id: str | None = None,
) -> Tuple[list[Watchlist], int]:
    """List watchlists with pagination, optionally filtered by user."""
    query = db.query(Watchlist)
    if user_id:
        query = query.filter(Watchlist.user_id == user_id)
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
    nuts_prefixes: Optional[list[str]] = None,
    sources: Optional[list[str]] = None,
    enabled: Optional[bool] = None,
    notify_email: Optional[str] = None,
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
    if nuts_prefixes is not None:
        wl.nuts_prefixes = _join_array(nuts_prefixes)
    if sources is not None:
        wl.sources = _join_sources_json(sources)
    if enabled is not None:
        wl.enabled = enabled
    if notify_email is not None:
        wl.notify_email = notify_email if notify_email else None
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
    Add SQL filters for keyword matching (title OR description).
    Returns (modified_query, matched_keywords_list_for_explanation).
    """
    if not keywords:
        return query, []

    keyword_conditions = []
    for keyword in keywords:
        keyword_conditions.append(Notice.title.ilike(f"%{keyword}%"))
        keyword_conditions.append(Notice.description.ilike(f"%{keyword}%"))

    if keyword_conditions:
        query = query.filter(or_(*keyword_conditions))

    return query, keywords


def _match_countries_sql(query, countries: list[str]) -> Tuple[Any, Optional[str]]:
    """Add SQL filter for country matching via NUTS codes (JSON array).
    NUTS codes start with 2-letter country code (e.g. BE, FR, NL)."""
    if not countries:
        return query, None
    # Match NUTS codes containing country prefix in JSON array
    country_conditions = []
    for c in countries:
        country_conditions.append(
            cast(Notice.nuts_codes, String).ilike(f'%"{c.upper()}%')
        )
    if country_conditions:
        query = query.filter(or_(*country_conditions))
    return query, countries[0] if countries else None


def _match_cpv_prefixes_sql(query, cpv_prefixes: list[str]) -> Tuple[Any, list[str]]:
    """
    Add SQL filters for CPV prefix matching (main or additional).
    Returns (modified_query, matched_prefixes_for_explanation).
    """
    if not cpv_prefixes:
        return query, []

    cpv_conditions = []
    for prefix in cpv_prefixes:
        prefix_clean = prefix.replace("-", "").strip()
        if not prefix_clean:
            continue
        # Match main CPV (normalized, no hyphens)
        cpv_conditions.append(
            func.replace(
                func.replace(Notice.cpv_main_code, "-", ""), " ", ""
            ).like(f"{prefix_clean}%")
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
                    func.replace(
                        func.replace(NoticeCpvAdditional.cpv_code, "-", ""), " ", ""
                    ).like(f"{prefix_clean}%")
                )
        if additional_conditions:
            cpv_conditions.extend(additional_conditions)
        # Use group_by(Notice.id) instead of .distinct() to avoid
        # "could not identify an equality operator for type json" on JSON columns.
        query = query.filter(or_(*cpv_conditions)).group_by(Notice.id)

    return query, cpv_prefixes


def _match_sources_sql(query, sources: list[str]) -> Any:
    """
    Add SQL filter for source matching.
    Converts watchlist source identifiers (TED, BOSA) to ProcurementNotice.source values.
    """
    if not sources:
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


def _check_keyword_in_searchable_text(
    notice: Notice, keywords: list[str], db: Session
) -> list[str]:
    """
    Check if keywords appear in searchable text (title + raw_data + notice_detail).
    Returns list of matched keywords.
    """
    if not keywords:
        return []

    detail = db.query(NoticeDetail).filter(NoticeDetail.notice_id == notice.id).first()
    searchable_text = build_searchable_text(notice, detail)

    matched = []
    searchable_lower = searchable_text.lower()
    for keyword in keywords:
        if keyword.lower() in searchable_lower:
            matched.append(keyword)

    return matched


def refresh_watchlist_matches(db: Session, watchlist: Watchlist) -> dict[str, int]:
    """
    Recompute and store matches for a watchlist idempotently.
    Optimized: batch-loads NoticeDetail + NoticeCpvAdditional to avoid N+1.
    Returns dict with counts: matched, added.
    """
    keywords = _parse_array(watchlist.keywords)
    countries = _parse_array(watchlist.countries)
    cpv_prefixes = _parse_array(watchlist.cpv_prefixes)
    sources = _parse_sources_json(watchlist.sources)

    # Delete existing matches (idempotent)
    db.query(WatchlistMatch).filter(
        WatchlistMatch.watchlist_id == watchlist.id
    ).delete()

    query = db.query(Notice)
    query = _match_sources_sql(query, sources)
    query, matched_keywords_for_explanation = _match_keywords_sql(query, keywords)
    query, matched_country_for_explanation = _match_countries_sql(query, countries)
    query, matched_cpv_prefixes_for_explanation = _match_cpv_prefixes_sql(
        query, cpv_prefixes
    )

    candidate_notices = query.all()
    if not candidate_notices:
        watchlist.last_refresh_at = datetime.now(timezone.utc)
        db.commit()
        return {"matched": 0, "added": 0}

    candidate_ids = [n.id for n in candidate_notices]

    # Batch-load NoticeDetail for keyword deep-check (1 query instead of N)
    detail_map: dict[str, NoticeDetail] = {}
    if keywords:
        details = db.query(NoticeDetail).filter(
            NoticeDetail.notice_id.in_(candidate_ids)
        ).all()
        detail_map = {d.notice_id: d for d in details}

    # Batch-load additional CPVs (1 query instead of N)
    additional_cpv_map: dict[str, list[str]] = {}
    if cpv_prefixes:
        additional_rows = db.query(NoticeCpvAdditional).filter(
            NoticeCpvAdditional.notice_id.in_(candidate_ids)
        ).all()
        for row in additional_rows:
            additional_cpv_map.setdefault(row.notice_id, []).append(
                (row.cpv_code or "").replace("-", "").strip()
            )

    matched_count = 0
    for notice in candidate_notices:
        # Keyword deep-check using pre-loaded details
        matched_kw = []
        if keywords:
            detail = detail_map.get(notice.id)
            searchable_text = build_searchable_text(notice, detail).lower()
            matched_kw = [kw for kw in keywords if kw.lower() in searchable_text]
            if not matched_kw:
                continue  # At least one keyword must match (OR logic)

        # CPV prefix check using pre-loaded additional CPVs
        matched_cpv = []
        if cpv_prefixes:
            main_cpv = (notice.cpv_main_code or "").replace("-", "").strip()
            add_cpvs = additional_cpv_map.get(notice.id, [])
            for prefix in cpv_prefixes:
                prefix_clean = prefix.replace("-", "").strip()
                if not prefix_clean:
                    continue
                if main_cpv.startswith(prefix_clean):
                    matched_cpv.append(prefix)
                elif any(ac.startswith(prefix_clean) for ac in add_cpvs):
                    matched_cpv.append(prefix)

        matched_on = _build_matched_on_explanation(
            matched_kw if keywords else [],
            matched_country_for_explanation,
            matched_cpv if cpv_prefixes else [],
        )

        db.add(WatchlistMatch(
            watchlist_id=watchlist.id,
            notice_id=notice.id,
            matched_on=matched_on,
        ))
        matched_count += 1

    watchlist.last_refresh_at = datetime.now(timezone.utc)
    db.commit()

    return {"matched": matched_count, "added": matched_count}


def list_watchlist_matches(
    db: Session,
    watchlist_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[Tuple[Notice, str, int | None]], int]:
    """
    List stored matches for a watchlist with matched_on explanations and relevance scores.
    Returns ((notice, matched_on, relevance_score), total_count).
    """
    query = (
        db.query(Notice, WatchlistMatch.matched_on, WatchlistMatch.relevance_score)
        .join(WatchlistMatch, Notice.id == WatchlistMatch.notice_id)
        .filter(WatchlistMatch.watchlist_id == watchlist_id)
    )
    total = query.count()
    results = (
        query.order_by(
            WatchlistMatch.relevance_score.desc().nulls_last(),
            Notice.publication_date.desc().nulls_last(),
            Notice.updated_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return results, total



# ---------------------------------------------------------------------------
#  Bridge functions: direct-query for Aperçu/Nouveaux, match-table for Pertinence
# ---------------------------------------------------------------------------

def _apply_extra_filters(query, source=None, q=None, sort="date_desc", active_only=False):
    """Apply common extra filters and sorting to a Notice query."""
    if source:
        query = query.filter(Notice.source == source)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(
            Notice.title.ilike(term),
            Notice.description.ilike(term),
            cast(Notice.organisation_names, String).ilike(term),
        ))
    if active_only:
        from datetime import date as date_cls
        query = query.filter(Notice.deadline >= date_cls.today())

    total = query.count()

    if sort == "date_asc":
        query = query.order_by(Notice.publication_date.asc().nulls_last())
    elif sort == "deadline":
        query = query.order_by(Notice.deadline.asc().nulls_last())
    elif sort == "deadline_desc":
        query = query.order_by(Notice.deadline.desc().nulls_last())
    elif sort == "value_desc":
        query = query.order_by(Notice.estimated_value.desc().nulls_last())
    else:
        query = query.order_by(Notice.publication_date.desc().nulls_last(), Notice.created_at.desc())

    return query, total


def _build_watchlist_query(db: Session, watchlist: Watchlist):
    """Build a Notice query from watchlist filters — direct SQL, no match table."""
    keywords = _parse_array(watchlist.keywords)
    countries = _parse_array(watchlist.countries)
    cpv_prefixes = _parse_array(watchlist.cpv_prefixes)
    sources = _parse_sources_json(watchlist.sources)

    query = db.query(Notice)
    query = _match_sources_sql(query, sources)
    query, _ = _match_keywords_sql(query, keywords)
    query, _ = _match_countries_sql(query, countries)
    query, _ = _match_cpv_prefixes_sql(query, cpv_prefixes)
    return query


def list_notices_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    limit: int = 100,
    offset: int = 0,
    source: str | None = None,
    q: str | None = None,
    sort: str = "date_desc",
    active_only: bool = False,
) -> Tuple[list[Notice], int]:
    """
    Get notices matching a watchlist's filters via direct SQL query.
    Fast read-only — no refresh, no match table.
    """
    query = _build_watchlist_query(db, watchlist)
    query, total = _apply_extra_filters(query, source, q, sort, active_only)
    notices = query.offset(offset).limit(limit).all()
    return notices, total


def list_new_since_for_watchlist(
    db: Session,
    watchlist: Watchlist,
    limit: int = 100,
    offset: int = 0,
    source: str | None = None,
    q: str | None = None,
    sort: str = "date_desc",
    active_only: bool = False,
) -> Tuple[list[Notice], int]:
    """
    Get NEW notices matching a watchlist — created since last_refresh_at.
    Direct SQL query, no match table.
    """
    cutoff = watchlist.last_refresh_at
    if not cutoff:
        return list_notices_for_watchlist(db, watchlist, limit, offset, source, q, sort, active_only)

    query = _build_watchlist_query(db, watchlist)
    query = query.filter(Notice.created_at > cutoff)
    query, total = _apply_extra_filters(query, source, q, sort, active_only)
    notices = query.offset(offset).limit(limit).all()
    return notices, total


def list_all_watchlists(db: Session, watchlist_id: str | None = None) -> list[Watchlist]:
    """List all watchlists, optionally filtered by id."""
    query = db.query(Watchlist)
    if watchlist_id:
        query = query.filter(Watchlist.id == watchlist_id)
    return query.order_by(Watchlist.created_at.desc()).all()
