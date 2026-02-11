"""Watchlist matcher: match new notices to enabled watchlists and send consolidated email digests.

Key behaviors:
- 1 email per user (consolidated across all watchlists)
- Auto-resolve email from user account if notify_email not set on watchlist
- Always send digest if there are open matches (reminder), even without new ones
- New matches are highlighted, existing open matches shown as reminders

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


# ── Resolve user email ───────────────────────────────────────────────

def _resolve_email(db: Session, watchlist: Watchlist) -> Optional[str]:
    """Get email for digest: notify_email on watchlist, or user's account email."""
    # 1. Explicit notify_email on watchlist
    email = getattr(watchlist, "notify_email", None)
    if email:
        return email

    # 2. Fall back to user account email
    user_id = getattr(watchlist, "user_id", None)
    if user_id:
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.email:
            return user.email

    return None


def _resolve_user_name(db: Session, watchlist: Watchlist) -> str:
    """Get display name for email greeting."""
    user_id = getattr(watchlist, "user_id", None)
    if user_id:
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return getattr(user, "full_name", None) or user.email.split("@")[0]
    return ""


# ── Get existing open matches for reminder ───────────────────────────

def _get_open_matches(db: Session, watchlist: Watchlist, limit: int = 20) -> list[Notice]:
    """Get existing matched notices that are still open (deadline in future or no deadline)."""
    now = datetime.now(timezone.utc).date()
    query = (
        db.query(Notice)
        .join(WatchlistMatch, WatchlistMatch.notice_id == Notice.id)
        .filter(WatchlistMatch.watchlist_id == watchlist.id)
        .filter(
            or_(
                Notice.deadline.is_(None),
                Notice.deadline >= now,
            )
        )
        .order_by(Notice.deadline.asc().nullslast())
        .limit(limit)
    )
    return query.all()


# ── Core matching ────────────────────────────────────────────────────

def match_watchlist(
    db: Session,
    watchlist: Watchlist,
    since: Optional[datetime] = None,
) -> list[Notice]:
    """Find new notices matching watchlist, store matches with relevance score (dedup), update last_refresh_at."""
    from app.services.relevance_scoring import calculate_relevance_score

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

        score, score_explanation = calculate_relevance_score(notice, watchlist)

        match = WatchlistMatch(
            watchlist_id=watchlist.id,
            notice_id=notice.id,
            matched_on=explanation,
            relevance_score=score,
        )
        db.add(match)
        new_matches.append(notice)

    watchlist.last_refresh_at = datetime.now(timezone.utc)
    db.commit()

    return new_matches


def _notice_to_email_dict(notice: Notice, is_new: bool = False) -> dict[str, Any]:
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
        "is_new": is_new,
    }


# ── Consolidated per-user digest ─────────────────────────────────────

def run_watchlist_matcher(db: Session) -> dict[str, Any]:
    """
    Run matcher for ALL enabled watchlists, then send ONE consolidated
    email per user (not per watchlist).

    Flow:
      1. For each enabled watchlist: match NEW notices + get existing OPEN matches
      2. Group results by user email (auto-resolved from user account)
      3. For each user with any matches (new or open): send 1 consolidated digest
    """
    watchlists = db.query(Watchlist).filter(Watchlist.enabled == True).all()

    results = {
        "watchlists_processed": 0,
        "total_new_matches": 0,
        "total_open_matches": 0,
        "emails_sent": 0,
        "details": [],
    }

    # Step 1: Match all watchlists, collect results grouped by user email
    user_digests: dict[str, list[dict[str, Any]]] = defaultdict(list)
    user_names: dict[str, str] = {}

    for wl in watchlists:
        try:
            # 1a. Find new matches
            new_matches = match_watchlist(db, wl)

            # 1b. Get all open matches (includes new ones + existing reminders)
            open_matches = _get_open_matches(db, wl, limit=20)

            # Track which notice IDs are new for highlighting
            new_ids = {n.id for n in new_matches}

            detail = {
                "watchlist_id": wl.id,
                "watchlist_name": wl.name,
                "new_matches": len(new_matches),
                "open_matches": len(open_matches),
                "email_sent": False,
            }

            # 1c. Resolve email (watchlist notify_email → user account email)
            email_addr = _resolve_email(db, wl)

            # 1d. Check if user's plan allows email digest
            can_send_email = True
            user_id = getattr(wl, "user_id", None)
            if user_id:
                from app.services.subscription import effective_plan as _eff_plan, get_plan_limits as _get_limits
                user_obj = db.query(User).filter(User.id == user_id).first()
                if user_obj:
                    plan_limits = _get_limits(_eff_plan(user_obj))
                    can_send_email = plan_limits.email_digest

            if email_addr and open_matches and can_send_email:
                email_data = [
                    _notice_to_email_dict(n, is_new=(n.id in new_ids))
                    for n in open_matches
                ]
                user_digests[email_addr].append({
                    "watchlist": wl,
                    "watchlist_name": wl.name,
                    "watchlist_keywords": wl.keywords or "",
                    "matches": email_data,
                    "new_count": len(new_matches),
                })
                detail["queued_for_digest"] = True
                detail["resolved_email"] = email_addr

                if email_addr not in user_names:
                    user_names[email_addr] = _resolve_user_name(db, wl)

            elif not email_addr:
                detail["skipped_reason"] = "no email (no notify_email and no user account)"

            elif not open_matches:
                detail["skipped_reason"] = "no open matches"

            elif not can_send_email:
                detail["skipped_reason"] = "plan does not include email digest"

            results["watchlists_processed"] += 1
            results["total_new_matches"] += len(new_matches)
            results["total_open_matches"] += len(open_matches)
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
            user_name = user_names.get(email_addr, email_addr.split("@")[0])
            total_matches = sum(len(wr["matches"]) for wr in wl_results)
            total_new = sum(wr.get("new_count", 0) for wr in wl_results)

            send_consolidated_digest(
                to_address=email_addr,
                user_name=user_name,
                watchlist_results=wl_results,
            )

            results["emails_sent"] += 1
            logger.info(
                f"Consolidated digest → {email_addr}: "
                f"{total_matches} matches ({total_new} new) from {len(wl_results)} watchlist(s)"
            )

            wl_ids_sent = {wr["watchlist"].id for wr in wl_results}
            for d in results["details"]:
                if d.get("watchlist_id") in wl_ids_sent:
                    d["email_sent"] = True

        except Exception as e:
            logger.error(f"Failed to send consolidated digest to {email_addr}: {e}")
            wl_ids = {wr["watchlist"].id for wr in wl_results}
            for d in results["details"]:
                if d.get("watchlist_id") in wl_ids:
                    d["email_error"] = str(e)

    return results
