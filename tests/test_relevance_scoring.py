"""Tests for relevance scoring engine."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock


from app.services.relevance_scoring import (
    calculate_relevance_score,
    _keyword_score,
    _cpv_score,
    _geo_score_watchlist,
    _recency_score,
)


def _make_notice(**kwargs):
    """Create a mock notice object."""
    notice = MagicMock()
    notice.title = kwargs.get("title", "")
    notice.description = kwargs.get("description", "")
    notice.cpv_main_code = kwargs.get("cpv_main_code", "")
    notice.nuts_codes = kwargs.get("nuts_codes", [])
    notice.deadline = kwargs.get("deadline", None)
    notice.estimated_value = kwargs.get("estimated_value", None)
    return notice


def _make_watchlist(**kwargs):
    """Create a mock watchlist object."""
    wl = MagicMock()
    wl.keywords = kwargs.get("keywords", None)
    wl.cpv_prefixes = kwargs.get("cpv_prefixes", None)
    wl.nuts_prefixes = kwargs.get("nuts_prefixes", None)
    wl.countries = kwargs.get("countries", None)
    return wl


# --- Keyword scoring ---

class TestKeywordScore:
    def test_no_keywords(self):
        notice = _make_notice(title="Nettoyage de bureaux")
        score, matched = _keyword_score(notice, [])
        assert score == 0
        assert matched == []

    def test_keyword_in_title(self):
        notice = _make_notice(title="Nettoyage de bureaux à Bruxelles")
        score, matched = _keyword_score(notice, ["nettoyage"])
        assert score == 12
        assert "nettoyage" in matched

    def test_keyword_in_description_only(self):
        notice = _make_notice(title="Marché public", description="Nettoyage de bureaux")
        score, matched = _keyword_score(notice, ["nettoyage"])
        assert score == 6
        assert "nettoyage" in matched

    def test_multiple_keywords_in_title(self):
        notice = _make_notice(title="Nettoyage de bureaux et entretien des locaux")
        score, matched = _keyword_score(notice, ["nettoyage", "entretien"])
        assert score == 24  # 12 + 12
        assert len(matched) == 2

    def test_keywords_capped_at_30(self):
        notice = _make_notice(title="Construction rénovation bâtiment travaux publics")
        score, matched = _keyword_score(notice, ["construction", "rénovation", "bâtiment", "travaux"])
        assert score == 30  # Capped (4 * 12 = 48 -> capped at 30)

    def test_no_match(self):
        notice = _make_notice(title="Fourniture de matériel informatique")
        score, matched = _keyword_score(notice, ["nettoyage"])
        assert score == 0
        assert matched == []


# --- CPV scoring ---

class TestCpvScore:
    def test_no_cpv(self):
        notice = _make_notice(cpv_main_code="45000000")
        score, matched = _cpv_score(notice, [])
        assert score == 0

    def test_exact_match(self):
        notice = _make_notice(cpv_main_code="45000000-7")
        score, matched = _cpv_score(notice, ["45000000"])
        assert score == 20

    def test_division_match(self):
        notice = _make_notice(cpv_main_code="45233120-6")
        score, matched = _cpv_score(notice, ["45233"])
        assert score == 15

    def test_group_match(self):
        notice = _make_notice(cpv_main_code="45233120-6")
        score, matched = _cpv_score(notice, ["452"])
        assert score == 12

    def test_broad_match(self):
        notice = _make_notice(cpv_main_code="45233120-6")
        score, matched = _cpv_score(notice, ["45"])
        assert score == 8

    def test_no_match(self):
        notice = _make_notice(cpv_main_code="45000000")
        score, matched = _cpv_score(notice, ["72"])
        assert score == 0


# --- Geographic scoring ---

class TestGeoScore:
    def test_nuts_exact_match(self):
        notice = _make_notice(nuts_codes=["BE100"])
        score, matched = _geo_score_watchlist(notice, ["be100"], [])
        assert score == 10

    def test_nuts_prefix_match(self):
        notice = _make_notice(nuts_codes=["BE211"])
        score, matched = _geo_score_watchlist(notice, ["be2"], [])
        assert score == 10

    def test_country_match(self):
        notice = _make_notice(nuts_codes=["BE100"])
        score, matched = _geo_score_watchlist(notice, [], ["BE"])
        assert score == 7

    def test_no_match(self):
        notice = _make_notice(nuts_codes=["FR100"])
        score, matched = _geo_score_watchlist(notice, ["be"], ["BE"])
        assert score == 0


# --- Recency scoring ---

class TestRecencyScore:
    def test_no_deadline(self):
        notice = _make_notice(deadline=None)
        assert _recency_score(notice) == 5

    def test_ample_time(self):
        notice = _make_notice(deadline=datetime.now(timezone.utc) + timedelta(days=30))
        assert _recency_score(notice) == 10

    def test_medium_time(self):
        notice = _make_notice(deadline=datetime.now(timezone.utc) + timedelta(days=10))
        assert _recency_score(notice) == 7

    def test_short_time(self):
        notice = _make_notice(deadline=datetime.now(timezone.utc) + timedelta(days=5))
        assert _recency_score(notice) == 4

    def test_urgent(self):
        notice = _make_notice(deadline=datetime.now(timezone.utc) + timedelta(days=1))
        assert _recency_score(notice) == 1


# --- Full scoring ---

class TestCalculateRelevanceScore:
    def test_perfect_match(self):
        """Notice matches all dimensions -> high score."""
        notice = _make_notice(
            title="Nettoyage de bureaux à Bruxelles",
            cpv_main_code="90910000-9",
            nuts_codes=["BE100"],
            deadline=datetime.now(timezone.utc) + timedelta(days=30),
        )
        watchlist = _make_watchlist(
            keywords="nettoyage,bureaux",
            cpv_prefixes="90910000",
            nuts_prefixes="BE1",
            countries="BE",
        )
        score, explanation = calculate_relevance_score(notice, watchlist)
        assert score >= 50  # Keywords (24) + CPV (20) + Geo (10) + Recency (10) = 64
        assert "mots-clés" in explanation
        assert "CPV" in explanation

    def test_keyword_only_match(self):
        """Only keyword match -> moderate score."""
        notice = _make_notice(
            title="Nettoyage de bureaux",
            cpv_main_code="90910000",
            nuts_codes=[],
            deadline=None,
        )
        watchlist = _make_watchlist(
            keywords="nettoyage",
        )
        score, explanation = calculate_relevance_score(notice, watchlist)
        assert 12 <= score <= 25  # keyword (12) + recency (5) = 17
        assert "mots-clés" in explanation

    def test_no_filters(self):
        """Watchlist with no filters -> only recency points."""
        notice = _make_notice(deadline=datetime.now(timezone.utc) + timedelta(days=30))
        watchlist = _make_watchlist()
        score, explanation = calculate_relevance_score(notice, watchlist)
        assert score == 10  # Only recency

    def test_score_capped_at_100(self):
        """Score never exceeds 100."""
        notice = _make_notice(
            title="nettoyage entretien propreté bureaux locaux",
            cpv_main_code="90910000-9",
            nuts_codes=["BE100"],
            deadline=datetime.now(timezone.utc) + timedelta(days=30),
        )
        watchlist = _make_watchlist(
            keywords="nettoyage,entretien,propreté,bureaux,locaux",
            cpv_prefixes="90910000",
            nuts_prefixes="BE1",
        )
        score, _ = calculate_relevance_score(notice, watchlist)
        assert score <= 100
