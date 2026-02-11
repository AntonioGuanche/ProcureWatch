"""Relevance scoring engine for watchlist → notice matches.

Computes a 0–100 score based on match quality across multiple dimensions:
  - Keyword match quality (40 pts)
  - CPV code match (25 pts)
  - Geographic match (20 pts)
  - Recency / deadline proximity (15 pts)

Used by watchlist_matcher to assign scores to each WatchlistMatch record.
"""
import re
from datetime import datetime, timezone
from typing import Any, Optional


def _parse_csv(val: Optional[str]) -> list[str]:
    if not val:
        return []
    return [v.strip().lower() for v in val.split(",") if v.strip()]


def _get_text_fields(notice: Any) -> str:
    """Concatenate title + description for keyword matching."""
    parts = []
    title = getattr(notice, "title", None)
    if title:
        parts.append(str(title))
    desc = getattr(notice, "description", None)
    if desc:
        parts.append(str(desc))
    return " ".join(parts).lower()


def _keyword_score(notice: Any, keywords: list[str]) -> tuple[int, list[str]]:
    """Score keyword matches (0–40 pts). Returns (score, matched_keywords).

    - Each keyword found in title: +15 pts (title is highest signal)
    - Each keyword found only in description: +8 pts
    - Capped at 40.
    """
    if not keywords:
        return 0, []

    title = (getattr(notice, "title", "") or "").lower()
    desc = (getattr(notice, "description", "") or "").lower()

    score = 0
    matched = []
    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if kw_lower in title:
            score += 15
            matched.append(kw)
        elif kw_lower in desc:
            score += 8
            matched.append(kw)

    return min(score, 40), matched


def _cpv_score(notice: Any, cpv_prefixes: list[str]) -> tuple[int, list[str]]:
    """Score CPV code match (0–25 pts). Returns (score, matched_prefixes).

    - Exact match (full code): 25 pts
    - Division match (first 2 digits): 20 pts
    - Group match (first 3 digits): 15 pts
    - Broader match (first 1-2 chars): 10 pts
    """
    if not cpv_prefixes:
        return 0, []

    notice_cpv = (getattr(notice, "cpv_main_code", "") or "").replace("-", "").strip()
    if not notice_cpv:
        return 0, []

    best_score = 0
    matched = []
    for prefix in cpv_prefixes:
        p_clean = prefix.replace("-", "").strip()
        if not p_clean:
            continue

        if notice_cpv == p_clean or notice_cpv.startswith(p_clean):
            overlap = len(p_clean)
            if overlap >= 8:
                s = 25  # Exact/nearly exact
            elif overlap >= 5:
                s = 20  # Division level
            elif overlap >= 3:
                s = 15  # Group level
            else:
                s = 10  # Broader
            if s > best_score:
                best_score = s
                matched = [prefix]

    return best_score, matched


def _geo_score(notice: Any, nuts_prefixes: list[str], countries: list[str]) -> tuple[int, list[str]]:
    """Score geographic match (0–20 pts). Returns (score, matched_regions).

    - NUTS exact/prefix match: 20 pts
    - Country match (from NUTS codes): 15 pts
    """
    nuts_codes = getattr(notice, "nuts_codes", None) or []
    if not isinstance(nuts_codes, list):
        nuts_codes = []

    matched = []

    # NUTS prefix match
    if nuts_prefixes:
        for notice_nut in nuts_codes:
            n = str(notice_nut).strip().upper()
            for prefix in nuts_prefixes:
                p = prefix.strip().upper()
                if n.startswith(p):
                    matched.append(p)
                    return 20, matched

    # Country match (first 2 chars of NUTS code = country)
    if countries:
        country_set = {c.strip().upper() for c in countries}
        for notice_nut in nuts_codes:
            n = str(notice_nut).strip().upper()
            if len(n) >= 2 and n[:2] in country_set:
                matched.append(n[:2])
                return 15, matched

    return 0, matched


def _recency_score(notice: Any) -> int:
    """Score based on deadline proximity (0–15 pts).

    - Deadline > 14 days away: 15 pts (ample time to respond)
    - Deadline 7–14 days: 10 pts
    - Deadline 3–7 days: 5 pts
    - Deadline < 3 days or past: 2 pts
    - No deadline: 8 pts (neutral)
    """
    deadline = getattr(notice, "deadline", None)
    if not deadline:
        return 8

    now = datetime.now(timezone.utc)
    if hasattr(deadline, "tzinfo") and deadline.tzinfo is None:
        # Naive datetime — assume UTC
        from datetime import timezone as tz
        deadline = deadline.replace(tzinfo=tz.utc)

    days_left = (deadline - now).days

    if days_left > 14:
        return 15
    elif days_left >= 7:
        return 10
    elif days_left >= 3:
        return 5
    else:
        return 2


def calculate_relevance_score(
    notice: Any,
    watchlist: Any,
) -> tuple[int, str]:
    """Calculate relevance score (0–100) for a notice against a watchlist.

    Returns:
        (score, explanation) — score 0–100 and human-readable breakdown.
    """
    keywords = _parse_csv(getattr(watchlist, "keywords", None))
    cpv_prefixes = _parse_csv(getattr(watchlist, "cpv_prefixes", None))
    nuts_prefixes = _parse_csv(getattr(watchlist, "nuts_prefixes", None))
    countries = _parse_csv(getattr(watchlist, "countries", None))

    kw_pts, kw_matched = _keyword_score(notice, keywords)
    cpv_pts, cpv_matched = _cpv_score(notice, cpv_prefixes)
    geo_pts, geo_matched = _geo_score(notice, nuts_prefixes, countries)
    recency_pts = _recency_score(notice)

    total = kw_pts + cpv_pts + geo_pts + recency_pts

    # Build explanation
    parts = []
    if kw_matched:
        parts.append(f"keywords: {', '.join(kw_matched)} ({kw_pts}pts)")
    elif keywords:
        parts.append(f"keywords: none matched ({kw_pts}pts)")
    if cpv_matched:
        parts.append(f"CPV: {', '.join(cpv_matched)} ({cpv_pts}pts)")
    if geo_matched:
        parts.append(f"geo: {', '.join(geo_matched)} ({geo_pts}pts)")
    parts.append(f"recency: {recency_pts}pts")

    explanation = ", ".join(parts)
    return min(total, 100), explanation
