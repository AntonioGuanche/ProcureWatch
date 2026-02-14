"""Tests for watchlist value range criteria (migration 014 feature)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource
from tests.conftest import make_notice, seed_notices


@pytest.fixture()
def db():
    """In-memory SQLite session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Schema validation ────────────────────────────────────────────────

@pytest.mark.unit
class TestWatchlistSchema:
    """WatchlistCreate/Update schema validates value fields."""

    def test_create_schema_accepts_value_min_max(self):
        from app.api.schemas.watchlist import WatchlistCreate
        wl = WatchlistCreate(
            name="Test",
            value_min=10000.0,
            value_max=500000.0,
        )
        assert wl.value_min == 10000.0
        assert wl.value_max == 500000.0

    def test_create_schema_defaults_none(self):
        from app.api.schemas.watchlist import WatchlistCreate
        wl = WatchlistCreate(name="Test")
        assert wl.value_min is None
        assert wl.value_max is None

    def test_create_schema_rejects_negative(self):
        from app.api.schemas.watchlist import WatchlistCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            WatchlistCreate(name="Test", value_min=-100)

    def test_update_schema_allows_value_fields(self):
        from app.api.schemas.watchlist import WatchlistUpdate
        wl = WatchlistUpdate(value_min=5000.0, value_max=None)
        assert wl.value_min == 5000.0
        assert wl.value_max is None


# ── Watchlist matcher explanation ────────────────────────────────────

@pytest.mark.unit
class TestMatcherExplanation:
    """Watchlist matcher builds correct explanation with value range."""

    def test_explanation_includes_value_range(self):
        from app.services.watchlist_matcher import _build_explanation

        wl = MagicMock()
        wl.keywords = "test"
        wl.cpv_prefixes = ""
        wl.countries = ""
        wl.nuts_prefixes = ""
        wl.value_min = 10000
        wl.value_max = 500000

        explanation = _build_explanation(wl)
        assert "10" in explanation  # formatted with thousands separator
        assert "500" in explanation

    def test_explanation_value_min_only(self):
        from app.services.watchlist_matcher import _build_explanation

        wl = MagicMock()
        wl.keywords = []
        wl.cpv_prefixes = ""
        wl.countries = ""
        wl.nuts_prefixes = ""
        wl.value_min = 10000
        wl.value_max = None

        explanation = _build_explanation(wl)
        assert "10" in explanation
        assert "∞" in explanation

    def test_explanation_no_value(self):
        from app.services.watchlist_matcher import _build_explanation

        wl = MagicMock()
        wl.keywords = "construction"
        wl.cpv_prefixes = ""
        wl.countries = ""
        wl.nuts_prefixes = ""
        wl.value_min = None
        wl.value_max = None

        explanation = _build_explanation(wl)
        assert "value" not in explanation.lower() or "valeur" not in explanation.lower()


# ── Search service value range (integration with build_search_query) ─

@pytest.mark.unit
class TestSearchValueRange:
    """Verify value range filters in build_search_query."""

    def test_no_value_filter_returns_all(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("5000")),
            make_notice(estimated_value=None),
        ])
        query, _ = build_search_query(db)
        assert query.count() == 2

    def test_value_min_excludes_lower(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(title="Small", estimated_value=Decimal("1000")),
            make_notice(title="Big", estimated_value=Decimal("100000")),
        ])
        query, _ = build_search_query(db, value_min=50000)
        results = query.all()
        assert len(results) == 1
        assert results[0].title == "Big"

    def test_value_max_excludes_higher(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(title="Small", estimated_value=Decimal("1000")),
            make_notice(title="Big", estimated_value=Decimal("100000")),
        ])
        query, _ = build_search_query(db, value_max=50000)
        results = query.all()
        assert len(results) == 1
        assert results[0].title == "Small"

    def test_zero_value_min_is_noop(self, db):
        """value_min=0 should still match everything with a value."""
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("0")),
            make_notice(estimated_value=Decimal("50000")),
        ])
        query, _ = build_search_query(db, value_min=0)
        assert query.count() == 2
