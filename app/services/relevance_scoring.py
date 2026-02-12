"""Relevance scoring engine for watchlist → notice matches.

Computes a 0–100 score based on two layers:

Layer 1 — Watchlist match quality (0–70 pts):
  - Keyword match quality (30 pts)
  - CPV code match (20 pts)
  - Geographic match via watchlist filters (10 pts)
  - Recency / deadline proximity (10 pts)

Layer 2 — Company profile boost (0–30 pts):
  - Geo proximity: distance from user's address to notice NUTS centroid (0–15 pts)
  - NACE↔CPV: user's business activity matches notice category (0–15 pts)

Total = min(Layer1 + Layer2, 100).

Used by:
  - watchlist_matcher (import pipeline) → stores score in WatchlistMatch
  - refresh_watchlist_matches (manual Refresh button) → same
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.geo import closest_distance_km
from app.utils.nace_cpv import nace_matches_cpv, cpv_prefixes_for_nace_list

logger = logging.getLogger(__name__)


def _parse_csv(val: Optional[str]) -> list[str]:
    if not val:
        return []
    return [v.strip().lower() for v in val.split(",") if v.strip()]


# ─── Layer 1: Watchlist match scoring ────────────────────────────────


def _keyword_score(notice: Any, keywords: list[str]) -> tuple[int, list[str]]:
    """Score keyword matches (0–30 pts). Returns (score, matched_keywords).

    - Each keyword found in title: +12 pts (title is highest signal)
    - Each keyword found only in description: +6 pts
    - Capped at 30.
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
            score += 12
            matched.append(kw)
        elif kw_lower in desc:
            score += 6
            matched.append(kw)

    return min(score, 30), matched


def _cpv_score(notice: Any, cpv_prefixes: list[str]) -> tuple[int, list[str]]:
    """Score CPV code match (0–20 pts). Returns (score, matched_prefixes).

    - Exact match (full code): 20 pts
    - Division match (first 2 digits): 15 pts
    - Group match (first 3 digits): 12 pts
    - Broader match (first 1-2 chars): 8 pts
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
                s = 20  # Exact/nearly exact
            elif overlap >= 5:
                s = 15  # Division level
            elif overlap >= 3:
                s = 12  # Group level
            else:
                s = 8   # Broader
            if s > best_score:
                best_score = s
                matched = [prefix]

    return best_score, matched


def _geo_score_watchlist(notice: Any, nuts_prefixes: list[str], countries: list[str]) -> tuple[int, list[str]]:
    """Score geographic match from watchlist filters (0–10 pts)."""
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
                    return 10, matched

    # Country match (first 2 chars of NUTS code = country)
    if countries:
        country_set = {c.strip().upper() for c in countries}
        for notice_nut in nuts_codes:
            n = str(notice_nut).strip().upper()
            if len(n) >= 2 and n[:2] in country_set:
                matched.append(n[:2])
                return 7, matched

    return 0, matched


def _recency_score(notice: Any) -> int:
    """Score based on deadline proximity (0–10 pts).

    - Deadline > 14 days away: 10 pts (ample time to respond)
    - Deadline 7–14 days: 7 pts
    - Deadline 3–7 days: 4 pts
    - Deadline < 3 days or past: 1 pt
    - No deadline: 5 pts (neutral)
    """
    deadline = getattr(notice, "deadline", None)
    if not deadline:
        return 5

    now = datetime.now(timezone.utc)
    if hasattr(deadline, "tzinfo") and deadline.tzinfo is None:
        from datetime import timezone as tz
        deadline = deadline.replace(tzinfo=tz.utc)

    days_left = (deadline - now).days

    if days_left > 14:
        return 10
    elif days_left >= 7:
        return 7
    elif days_left >= 3:
        return 4
    else:
        return 1


# ─── Layer 2: Company profile boost ─────────────────────────────────


def _geo_proximity_boost(
    notice: Any,
    user_lat: Optional[float],
    user_lng: Optional[float],
) -> tuple[int, Optional[str]]:
    """Boost based on distance from user's location to notice NUTS centroid (0–15 pts).

    - < 30 km:  15 pts  (local — very likely relevant)
    - < 75 km:  12 pts  (regional)
    - < 150 km: 8 pts   (inter-regional, e.g. Bruxelles→Liège)
    - < 300 km: 4 pts   (national, e.g. Bruxelles→Arlon)
    - > 300 km: 0 pts   (far away)
    """
    if user_lat is None or user_lng is None:
        return 0, None

    nuts_codes = getattr(notice, "nuts_codes", None) or []
    if not isinstance(nuts_codes, list) or not nuts_codes:
        return 0, None

    dist = closest_distance_km(user_lat, user_lng, nuts_codes)
    if dist is None:
        return 0, None

    if dist < 30:
        return 15, f"~{dist:.0f}km (local)"
    elif dist < 75:
        return 12, f"~{dist:.0f}km (régional)"
    elif dist < 150:
        return 8, f"~{dist:.0f}km"
    elif dist < 300:
        return 4, f"~{dist:.0f}km"
    else:
        return 0, f"~{dist:.0f}km (loin)"


def _nace_cpv_boost(
    notice: Any,
    nace_codes: Optional[str],
) -> tuple[int, Optional[str]]:
    """Boost when user's NACE business activity matches notice CPV (0–15 pts).

    - Direct NACE→CPV division match: 15 pts
    """
    if not nace_codes:
        return 0, None

    cpv_code = (getattr(notice, "cpv_main_code", "") or "").replace("-", "").strip()
    if not cpv_code or len(cpv_code) < 2:
        return 0, None

    if nace_matches_cpv(nace_codes, cpv_code):
        cpv_div = cpv_code[:2]
        return 15, f"NACE→CPV:{cpv_div}"

    return 0, None


# ─── Public API ──────────────────────────────────────────────────────


def calculate_relevance_score(
    notice: Any,
    watchlist: Any,
    user: Any = None,
) -> tuple[int, str]:
    """Calculate relevance score (0–100) for a notice against a watchlist.

    Args:
        notice: Notice ORM instance
        watchlist: Watchlist ORM instance
        user: Optional User ORM instance (for profile boost)

    Returns:
        (score, explanation) — score 0–100 and human-readable breakdown.
    """
    keywords = _parse_csv(getattr(watchlist, "keywords", None))
    cpv_prefixes = _parse_csv(getattr(watchlist, "cpv_prefixes", None))
    nuts_prefixes = _parse_csv(getattr(watchlist, "nuts_prefixes", None))
    countries = _parse_csv(getattr(watchlist, "countries", None))

    # Layer 1: watchlist match (0–70)
    kw_pts, kw_matched = _keyword_score(notice, keywords)
    cpv_pts, cpv_matched = _cpv_score(notice, cpv_prefixes)
    geo_pts, geo_matched = _geo_score_watchlist(notice, nuts_prefixes, countries)
    recency_pts = _recency_score(notice)

    layer1 = kw_pts + cpv_pts + geo_pts + recency_pts

    # Layer 2: profile boost (0–30)
    prox_pts, prox_detail = 0, None
    nace_pts, nace_detail = 0, None

    if user is not None:
        user_lat = getattr(user, "latitude", None)
        user_lng = getattr(user, "longitude", None)
        prox_pts, prox_detail = _geo_proximity_boost(notice, user_lat, user_lng)

        user_nace = getattr(user, "nace_codes", None)
        nace_pts, nace_detail = _nace_cpv_boost(notice, user_nace)

    layer2 = prox_pts + nace_pts
    total = min(layer1 + layer2, 100)

    # Build explanation
    parts = []
    if kw_matched:
        parts.append(f"mots-clés: {', '.join(kw_matched)} ({kw_pts})")
    elif keywords:
        parts.append(f"mots-clés: aucun ({kw_pts})")
    if cpv_matched:
        parts.append(f"CPV: {', '.join(cpv_matched)} ({cpv_pts})")
    if geo_matched:
        parts.append(f"zone: {', '.join(geo_matched)} ({geo_pts})")
    parts.append(f"délai: {recency_pts}")
    if prox_pts:
        parts.append(f"proximité: {prox_detail} (+{prox_pts})")
    if nace_pts:
        parts.append(f"activité: {nace_detail} (+{nace_pts})")

    explanation = " | ".join(parts)
    return total, explanation
