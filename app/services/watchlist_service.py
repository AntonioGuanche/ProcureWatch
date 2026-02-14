"""Service for matching notices to watchlists and storing matches."""
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import false, func, or_
from sqlalchemy.orm import Session

from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch
from app.models.notice import ProcurementNotice

# Map watchlist source identifiers (TED, BOSA) to notice.source column (ProcurementNotice schema)
WATCHLIST_SOURCE_TO_NOTICE_SOURCE = {
    "BOSA": "BOSA_EPROC",
    "TED": "TED_EU",
}


def _parse_keywords(value: Optional[str]) -> list[str]:
    """Parse comma-separated keywords; return empty list if None/empty."""
    if not value or not value.strip():
        return []
    return [k.strip() for k in value.split(",") if k.strip()]


def _parse_cpv_prefixes(value: Optional[str]) -> list[str]:
    """Parse comma-separated CPV prefixes; return empty list if None/empty."""
    if not value or not value.strip():
        return []
    return [p.strip().replace("-", "").replace(" ", "") for p in value.split(",") if p.strip()]


def _parse_sources(value: Optional[str]) -> list[str]:
    """Parse watchlist.sources (JSON array e.g. [\"TED\", \"BOSA\"]); default to [\"TED\", \"BOSA\"]."""
    if not value or not value.strip():
        return ["TED", "BOSA"]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(s).strip().upper() for s in parsed if str(s).strip()]
        return ["TED", "BOSA"]
    except (json.JSONDecodeError, TypeError):
        return ["TED", "BOSA"]


def _notice_sources_for_watchlist(sources: list[str]) -> list[str]:
    """Convert watchlist source identifiers to notice.source values (BOSA_EPROC, TED_EU)."""
    out = []
    for s in sources:
        notice_src = WATCHLIST_SOURCE_TO_NOTICE_SOURCE.get(s.upper())
        if notice_src and notice_src not in out:
            out.append(notice_src)
    return out if out else list(WATCHLIST_SOURCE_TO_NOTICE_SOURCE.values())


def _build_matched_on(keywords_matched: list[str], cpv_matched: list[str]) -> str:
    """Build explanation string for matched_on."""
    parts = []
    if keywords_matched:
        parts.append(f"keywords: {', '.join(keywords_matched)}")
    if cpv_matched:
        parts.append(f"CPV: {', '.join(cpv_matched)}")
    return ", ".join(parts) if parts else "match"


class WatchlistService:
    """Match notices to watchlists and persist matches."""

    def __init__(self, db: Session):
        self.db = db

    def find_matches(self, watchlist_id: str, dry_run: bool = False) -> dict[str, Any]:
        """
        Find notices matching the watchlist criteria, insert new matches, update last_refresh_at.
        Criteria: (title OR description) contains ANY keyword; cpv_main_code starts with ANY prefix;
        source in watchlist.sources (BOSA→BOSA_EPROC, TED→TED_EU); publication_date >= last_refresh_at (or all if null).
        Skips notices that already have a watchlist_match for this watchlist.
        If dry_run=True, does not persist matches or update last_refresh_at.
        Returns {"new_matches": N, "notices": [{"id", "title", "source", "publication_date"}, ...]}.
        """
        watchlist = self.db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not watchlist:
            return {"new_matches": 0, "notices": [], "error": "Watchlist not found"}

        keywords = _parse_keywords(watchlist.keywords)
        cpv_prefixes = _parse_cpv_prefixes(watchlist.cpv_prefixes)
        source_ids = _parse_sources(watchlist.sources)
        notice_sources = _notice_sources_for_watchlist(source_ids)
        cutoff = watchlist.last_refresh_at.date() if watchlist.last_refresh_at else None

        # Expand keywords with FR/NL/EN translations for multilingual matching
        original_keywords = list(keywords)  # keep originals for matched_on display
        from app.services.translation_service import expand_keywords_list
        expanded_keywords = expand_keywords_list(keywords) if keywords else []

        query = self.db.query(ProcurementNotice).filter(ProcurementNotice.source.in_(notice_sources))

        if cutoff is not None:
            query = query.filter(ProcurementNotice.publication_date >= cutoff)

        keyword_conditions = []
        if expanded_keywords:
            for k in expanded_keywords:
                if not k:
                    continue
                pattern = f"%{k}%"
                keyword_conditions.append(ProcurementNotice.title.ilike(pattern))
                keyword_conditions.append(ProcurementNotice.description.ilike(pattern))
        cpv_conditions = []
        if cpv_prefixes:
            for p in cpv_prefixes:
                if not p:
                    continue
                cpv_conditions.append(
                    func.replace(func.coalesce(ProcurementNotice.cpv_main_code, ""), "-", "").like(f"{p}%")
                )

        # OR logic: include notices that match keywords OR cpv (or both)
        if keyword_conditions and cpv_conditions:
            query = query.filter(or_(or_(*keyword_conditions), or_(*cpv_conditions)))
        elif keyword_conditions:
            query = query.filter(or_(*keyword_conditions))
        elif cpv_conditions:
            query = query.filter(or_(*cpv_conditions))
        else:
            # No criteria: no candidates
            query = query.filter(false())

        candidate_notices = query.distinct().all()
        existing_match_ids = {
            row[0]
            for row in self.db.query(WatchlistMatch.notice_id).filter(
                WatchlistMatch.watchlist_id == watchlist_id
            ).all()
        }

        new_matches: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for notice in candidate_notices:
            if notice.id in existing_match_ids:
                continue
            keywords_matched = []
            if expanded_keywords:
                title_lower = (notice.title or "").lower()
                desc_lower = (notice.description or "").lower()
                for k in expanded_keywords:
                    if k.lower() in title_lower or k.lower() in desc_lower:
                        keywords_matched.append(k)
            cpv_matched = []
            main_cpv = (notice.cpv_main_code or "").replace("-", "").replace(" ", "")
            if cpv_prefixes:
                for p in cpv_prefixes:
                    if p and main_cpv.startswith(p):
                        cpv_matched.append(p)
                        break
            # Include if (keywords matched) OR (cpv matched) or both
            if not ((expanded_keywords and keywords_matched) or (cpv_prefixes and cpv_matched)):
                continue

            matched_on = _build_matched_on(keywords_matched, cpv_matched)
            match = WatchlistMatch(
                watchlist_id=watchlist_id,
                notice_id=notice.id,
                matched_on=matched_on,
            )
            self.db.add(match)
            existing_match_ids.add(notice.id)
            new_matches.append({
                "id": notice.id,
                "title": notice.title,
                "source": notice.source,
                "publication_date": notice.publication_date.isoformat() if notice.publication_date else None,
            })

        if not dry_run:
            watchlist.last_refresh_at = now
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        else:
            self.db.rollback()

        return {"new_matches": len(new_matches), "notices": new_matches}

    def find_all_matches(self, dry_run: bool = False) -> dict[str, Any]:
        """
        Run find_matches for every watchlist and return aggregate stats.
        If dry_run=True, no changes are persisted.
        Returns {"watchlists": N, "total_new_matches": N, "by_watchlist": [{watchlist_id, new_matches, ...}]}.
        """
        watchlists = self.db.query(Watchlist).all()
        total_new = 0
        by_watchlist: list[dict[str, Any]] = []
        for wl in watchlists:
            result = self.find_matches(wl.id, dry_run=dry_run)
            new_count = result.get("new_matches", 0)
            total_new += new_count
            by_watchlist.append({
                "watchlist_id": wl.id,
                "watchlist_name": wl.name,
                "new_matches": new_count,
                "notices": result.get("notices", []),
            })
        return {
            "watchlists": len(watchlists),
            "total_new_matches": total_new,
            "by_watchlist": by_watchlist,
        }
