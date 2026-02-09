"""Watchlist matcher: match new notices to enabled watchlists and send email digests.

Called after each import run. For each enabled watchlist with a notify_email:
1. Find notices created since last_refresh_at that match the watchlist criteria
2. Store new matches in watchlist_matches (dedup via unique constraint)
3. Send email digest with new matches
4. Update last_refresh_at
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, cast, func, or_, String, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice as Notice, NoticeSource
from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch
from app.services.notification_service import send_watchlist_notification

logger = logging.getLogger(__name__)


def _parse_csv(val: Optional[str]) -> list[str]:
    """Parse comma-separated string to list."""
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def _source_map(src: str) -> Optional[str]:
    """Map watchlist source name to DB enum value."""
    s = src.strip().upper()
    if s in ("BOSA", "BOSA_EPROC"):
        return NoticeSource.BOSA_EPROC.value
    if s in ("TED", "TED_EU"):
        return NoticeSource.TED_EU.value
    return None


def _parse_sources_json(val: Optional[str]) -> list[str]:
    """Parse JSON array of sources."""
    if not val:
        return ["TED", "BOSA"]
    import json
    try:
        parsed = json.loads(val)
        return [str(s).strip() for s in parsed if str(s).strip()] if isinstance(parsed, list) else ["TED", "BOSA"]
    except (json.JSONDecodeError, TypeError):
        return ["TED", "BOSA"]


def _build_match_query(
    db: Session,
    watchlist: Watchlist,
    since: Optional[datetime] = None,
) -> Any:
    """
    Build SQLAlchemy query for notices matching watchlist criteria.
    If since is provided, only matches notices created after that time.
    """
    is_pg = db.bind.dialect.name == "postgresql"
    query = db.query(Notice)

    # Time filter: only new notices
    if since:
        query = query.filter(Notice.created_at > since)

    # Source filter
    sources = _parse_sources_json(watchlist.sources)
    if sources:
        db_sources = [s for s in (_source_map(src) for src in sources) if s]
        if db_sources:
            query = query.filter(Notice.source.in_(db_sources))

    # Keyword filter (OR across keywords, each matches title OR description)
    keywords = _parse_csv(watchlist.keywords)
    if keywords:
        kw_conditions = []
        for kw in keywords:
            like = f"%{kw}%"
            kw_conditions.append(Notice.title.ilike(like))
            kw_conditions.append(Notice.description.ilike(like))
        query = query.filter(or_(*kw_conditions))

    # CPV prefix filter (any prefix matches)
    cpv_prefixes = _parse_csv(watchlist.cpv_prefixes)
    if cpv_prefixes:
        cpv_conditions = []
        for prefix in cpv_prefixes:
            prefix_clean = prefix.replace("-", "").strip()
            if prefix_clean:
                cpv_conditions.append(
                    func.replace(func.coalesce(Notice.cpv_main_code, ""), "-", "").like(f"{prefix_clean}%")
                )
        if cpv_conditions:
            query = query.filter(or_(*cpv_conditions))

    # NUTS prefix filter
    nuts_prefixes = _parse_csv(getattr(watchlist, "nuts_prefixes", None))
    if nuts_prefixes and is_pg:
        nuts_conditions = []
        for prefix in nuts_prefixes:
            p = prefix.strip().upper()
            if p:
                nuts_conditions.append(
                    text(
                        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes::jsonb) AS nc "
                        "WHERE nc LIKE :nuts_p)"
                    ).bindparams(nuts_p=f"{p}%")
                )
        if nuts_conditions:
            query = query.filter(or_(*nuts_conditions))

    # Country filter (via NUTS codes — country = first 2 chars of NUTS)
    countries = _parse_csv(watchlist.countries)
    if countries:
        if is_pg:
            country_conditions = []
            for c in countries:
                country_conditions.append(
                    text(
                        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes::jsonb) AS nc "
                        "WHERE nc LIKE :country_p)"
                    ).bindparams(country_p=f"{c.upper()}%")
                )
            if country_conditions:
                query = query.filter(or_(*country_conditions))
        else:
            country_conditions = []
            for c in countries:
                country_conditions.append(
                    cast(Notice.nuts_codes, String).ilike(f'%"{c.upper()}%')
                )
            if country_conditions:
                query = query.filter(or_(*country_conditions))

    return query


def _build_explanation(watchlist: Watchlist) -> str:
    """Build human-readable explanation of match criteria."""
    parts = []
    kw = _parse_csv(watchlist.keywords)
    if kw:
        parts.append(f"keywords: {', '.join(kw)}")
    cpv = _parse_csv(watchlist.cpv_prefixes)
    if cpv:
        parts.append(f"CPV: {', '.join(cpv)}")
    nuts = _parse_csv(getattr(watchlist, "nuts_prefixes", None))
    if nuts:
        parts.append(f"NUTS: {', '.join(nuts)}")
    countries = _parse_csv(watchlist.countries)
    if countries:
        parts.append(f"countries: {', '.join(countries)}")
    return ", ".join(parts) if parts else "all notices"


def match_watchlist(
    db: Session,
    watchlist: Watchlist,
    since: Optional[datetime] = None,
) -> list[Notice]:
    """
    Find new notices matching watchlist criteria since last_refresh_at.
    Stores matches (dedup via try/except on unique constraint).
    Returns list of newly matched notices.
    """
    cutoff = since or watchlist.last_refresh_at
    query = _build_match_query(db, watchlist, since=cutoff)
    candidates = query.all()

    explanation = _build_explanation(watchlist)
    new_matches = []

    for notice in candidates:
        # Check if match already exists
        existing = (
            db.query(WatchlistMatch.id)
            .filter(
                WatchlistMatch.watchlist_id == watchlist.id,
                WatchlistMatch.notice_id == notice.id,
            )
            .first()
        )
        if existing:
            continue

        match = WatchlistMatch(
            watchlist_id=watchlist.id,
            notice_id=notice.id,
            matched_on=explanation,
        )
        db.add(match)
        new_matches.append(notice)

    # Update last_refresh_at
    watchlist.last_refresh_at = datetime.now(timezone.utc)
    db.commit()

    return new_matches


def _notice_to_email_dict(notice: Notice) -> dict[str, Any]:
    """Convert notice to dict for email template."""
    buyer = None
    if notice.organisation_names and isinstance(notice.organisation_names, dict):
        buyer = (
            notice.organisation_names.get("FR")
            or notice.organisation_names.get("NL")
            or notice.organisation_names.get("EN")
            or next(iter(notice.organisation_names.values()), None)
        )
    return {
        "title": notice.title,
        "buyer": buyer,
        "deadline": notice.deadline,
        "link": notice.url,
        "id": notice.id,
        "source": notice.source,
        "publication_date": notice.publication_date,
        "cpv": notice.cpv_main_code,
    }


def run_watchlist_matcher(db: Session) -> dict[str, Any]:
    """
    Run matcher for ALL enabled watchlists.
    For each: match new notices, send email if notify_email is set.
    Returns summary stats.
    """
    watchlists = db.query(Watchlist).filter(Watchlist.enabled == True).all()

    results = {
        "watchlists_processed": 0,
        "total_new_matches": 0,
        "emails_sent": 0,
        "details": [],
    }

    for wl in watchlists:
        try:
            new_matches = match_watchlist(db, wl)
            detail = {
                "watchlist_id": wl.id,
                "watchlist_name": wl.name,
                "new_matches": len(new_matches),
                "email_sent": False,
            }

            # Send email if configured and there are new matches
            if new_matches and getattr(wl, "notify_email", None):
                try:
                    email_data = [_notice_to_email_dict(n) for n in new_matches]
                    send_watchlist_notification(wl, email_data, to_address=wl.notify_email)
                    detail["email_sent"] = True
                    results["emails_sent"] += 1
                    logger.info(f"Sent {len(new_matches)} match(es) to {wl.notify_email} for watchlist '{wl.name}'")
                except Exception as e:
                    detail["email_error"] = str(e)
                    logger.error(f"Failed to send email for watchlist '{wl.name}': {e}")

            results["watchlists_processed"] += 1
            results["total_new_matches"] += len(new_matches)
            results["details"].append(detail)

        except Exception as e:
            logger.error(f"Error matching watchlist '{wl.name}': {e}")
            results["details"].append({
                "watchlist_id": wl.id,
                "watchlist_name": wl.name,
                "error": str(e),
            })

    return results
