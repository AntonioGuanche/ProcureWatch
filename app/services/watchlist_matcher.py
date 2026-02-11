"""Watchlist matcher: match new notices to enabled watchlists and send consolidated email digests.

Key change from v6: instead of 1 email per watchlist, we group all watchlists
by user and send 1 consolidated email per user.

Called after each import run via run_watchlist_matcher(db).
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, cast, func, or_, String, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice as Notice, NoticeSource
from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_csv(val: Optional[str]) -> list[str]:
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def _source_map(src: str) -> Optional[str]:
    s = src.strip().upper()
    if s in ("BOSA", "BOSA_EPROC"):
        return NoticeSource.BOSA_EPROC.value
    if s in ("TED", "TED_EU"):
        return NoticeSource.TED_EU.value
    return None


def _parse_sources_json(val: Optional[str]) -> list[str]:
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
    """Build SQLAlchemy query for notices matching watchlist criteria."""
    is_pg = db.bind.dialect.name == "postgresql"
    query = db.query(Notice)

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

    # CPV prefix filter
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
                        "notices.nuts_codes IS NOT NULL AND json_typeof(notices.nuts_codes) = 'array' "
                        "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes::jsonb) AS nc "
                        "WHERE nc LIKE :nuts_p)"
                    ).bindparams(nuts_p=f"{p}%")
                )
        if nuts_conditions:
            query = query.filter(or_(*nuts_conditions))

    # Country filter
    countries = _parse_csv(watchlist.countries)
    if countries:
        if is_pg:
            country_conditions = []
            for c in countries:
                country_conditions.append(
                    text(
                        "notices.nuts_codes IS NOT NULL AND json_typeof(notices.nuts_codes) = 'array' "
                        "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes::jsonb) AS nc "
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


# ── Core matching ────────────────────────────────────────────────────

def match_watchlist(
    db: Session,
    watchlist: Watchlist,
    since: Optional[datetime] = None,
) -> list[Notice]:
    """Find new notices matching watchlist, store matches (dedup), update last_refresh_at."""
    cutoff = since or watchlist.last_refresh_at
    query = _build_match_query(db, watchlist, since=cutoff)
    candidates = query.all()

    explanation = _build_explanation(watchlist)
    new_matches = []

    for notice in candidates:
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


# ── Consolidated per-user digest ─────────────────────────────────────

def run_watchlist_matcher(db: Session) -> dict[str, Any]:
    """
    Run matcher for ALL enabled watchlists, then send ONE consolidated
    email per user (not per watchlist).

    Flow:
      1. For each enabled watchlist: match new notices
      2. Group results by user (via notify_email or user_id)
      3. For each user with matches: send 1 consolidated email
    """
    watchlists = db.query(Watchlist).filter(Watchlist.enabled == True).all()

    results = {
        "watchlists_processed": 0,
        "total_new_matches": 0,
        "emails_sent": 0,
        "details": [],
    }

    # Step 1: Match all watchlists, collect results grouped by user email
    # Key: notify_email → list of { watchlist, new_matches }
    user_digests: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for wl in watchlists:
        try:
            new_matches = match_watchlist(db, wl)
            detail = {
                "watchlist_id": wl.id,
                "watchlist_name": wl.name,
                "new_matches": len(new_matches),
                "email_sent": False,
            }

            # Collect for consolidated digest
            if new_matches and getattr(wl, "notify_email", None):
                email_data = [_notice_to_email_dict(n) for n in new_matches]
                user_digests[wl.notify_email].append({
                    "watchlist": wl,
                    "watchlist_name": wl.name,
                    "watchlist_keywords": wl.keywords or "",
                    "matches": email_data,
                })
                detail["queued_for_digest"] = True

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

    # Step 2: Send consolidated email per user
    from app.services.notification_service import send_consolidated_digest

    for email_addr, wl_results in user_digests.items():
        try:
            # Try to get user name from the first watchlist's user
            user_name = ""
            first_wl = wl_results[0]["watchlist"]
            if hasattr(first_wl, "user_id") and first_wl.user_id:
                from app.models.user import User
                user = db.query(User).filter(User.id == first_wl.user_id).first()
                if user and hasattr(user, "full_name"):
                    user_name = user.full_name or user.email.split("@")[0]
                elif user:
                    user_name = user.email.split("@")[0]

            send_consolidated_digest(
                to_address=email_addr,
                user_name=user_name,
                watchlist_results=wl_results,
            )

            total_matches = sum(len(wr["matches"]) for wr in wl_results)
            n_wl = len(wl_results)
            results["emails_sent"] += 1
            logger.info(
                f"Consolidated digest → {email_addr}: "
                f"{total_matches} matches from {n_wl} watchlist(s)"
            )

            # Mark details as sent
            wl_ids_sent = {wr["watchlist"].id for wr in wl_results}
            for d in results["details"]:
                if d.get("watchlist_id") in wl_ids_sent:
                    d["email_sent"] = True

        except Exception as e:
            logger.error(f"Failed to send consolidated digest to {email_addr}: {e}")
            # Mark error on all related watchlists
            wl_ids = {wr["watchlist"].id for wr in wl_results}
            for d in results["details"]:
                if d.get("watchlist_id") in wl_ids:
                    d["email_error"] = str(e)

    return results
