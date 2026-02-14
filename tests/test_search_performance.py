"""Tests for search performance features: facets caching, value range filters."""
import time
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource
from tests.conftest import make_notice, seed_notices


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Facets caching ───────────────────────────────────────────────────

@pytest.mark.unit
class TestFacetsCache:
    """Facets caching with TTL."""

    def test_facets_returns_expected_keys(self, db):
        from app.services.search_service import get_facets, invalidate_facets_cache
        invalidate_facets_cache()

        seed_notices(db, [make_notice(notice_type="CONTRACT_NOTICE")])
        facets = get_facets(db)

        assert "total_notices" in facets
        assert "active_count" in facets
        assert "sources" in facets
        assert "top_cpv_divisions" in facets
        assert "top_nuts_countries" in facets
        assert "notice_types" in facets
        assert "date_range" in facets
        assert "deadline_range" in facets
        assert "value_range" in facets

    def test_facets_cache_returns_same_object(self, db):
        """Second call within TTL returns cached result."""
        from app.services.search_service import get_facets, invalidate_facets_cache
        invalidate_facets_cache()

        seed_notices(db, [make_notice()])
        result1 = get_facets(db)
        result2 = get_facets(db)
        assert result1 is result2  # same object from cache

    def test_facets_cache_invalidation(self, db):
        """invalidate_facets_cache() forces fresh computation."""
        from app.services.search_service import get_facets, invalidate_facets_cache
        invalidate_facets_cache()

        seed_notices(db, [make_notice()])
        result1 = get_facets(db)

        # Add more data
        seed_notices(db, [make_notice(), make_notice()])
        invalidate_facets_cache()
        result2 = get_facets(db)

        assert result2["total_notices"] == 3
        assert result1 is not result2


# ── Value range search ───────────────────────────────────────────────

@pytest.mark.unit
class TestValueRangeSearch:
    """Search with value_min/value_max filters."""

    def test_value_min_filter(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("5000")),
            make_notice(estimated_value=Decimal("50000")),
            make_notice(estimated_value=Decimal("500000")),
        ])
        query, _ = build_search_query(db, value_min=10000)
        assert query.count() == 2

    def test_value_max_filter(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("5000")),
            make_notice(estimated_value=Decimal("50000")),
            make_notice(estimated_value=Decimal("500000")),
        ])
        query, _ = build_search_query(db, value_max=100000)
        assert query.count() == 2

    def test_value_range_combined(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("5000")),
            make_notice(estimated_value=Decimal("50000")),
            make_notice(estimated_value=Decimal("500000")),
        ])
        query, _ = build_search_query(db, value_min=10000, value_max=100000)
        assert query.count() == 1

    def test_value_filter_ignores_null(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(estimated_value=Decimal("50000")),
            make_notice(estimated_value=None),
        ])
        query, _ = build_search_query(db, value_min=10000)
        assert query.count() == 1


# ── Active-only filter ───────────────────────────────────────────────

@pytest.mark.unit
class TestActiveOnlySearch:
    """active_only filter (deadline in the future)."""

    def test_active_only(self, db):
        from app.services.search_service import build_search_query

        future = datetime.now(timezone.utc) + timedelta(days=30)
        past = datetime.now(timezone.utc) - timedelta(days=30)

        seed_notices(db, [
            make_notice(deadline=future),
            make_notice(deadline=past),
            make_notice(deadline=None),
        ])
        query, _ = build_search_query(db, active_only=True)
        assert query.count() == 1


# ── Sort orders ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestSortOrders:
    """Various sort options work correctly."""

    def test_sort_value_desc(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(title="Low", estimated_value=Decimal("1000")),
            make_notice(title="High", estimated_value=Decimal("999000")),
            make_notice(title="Mid", estimated_value=Decimal("50000")),
        ])
        query, _ = build_search_query(db, sort="value_desc")
        rows = query.all()
        assert rows[0].title == "High"
        assert rows[-1].title == "Low"

    def test_sort_value_asc(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(title="Low", estimated_value=Decimal("1000")),
            make_notice(title="High", estimated_value=Decimal("999000")),
        ])
        query, _ = build_search_query(db, sort="value_asc")
        rows = query.all()
        assert rows[0].title == "Low"

    def test_sort_deadline(self, db):
        from app.services.search_service import build_search_query

        d1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        d2 = datetime(2025, 6, 1, tzinfo=timezone.utc)

        seed_notices(db, [
            make_notice(title="Later", deadline=d2),
            make_notice(title="Sooner", deadline=d1),
        ])
        query, _ = build_search_query(db, sort="deadline")
        rows = query.all()
        assert rows[0].title == "Sooner"


# ── Multi-source filter ──────────────────────────────────────────────

@pytest.mark.unit
class TestMultiSourceFilter:
    """sources parameter accepts list of sources."""

    def test_multi_source(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(source=NoticeSource.BOSA_EPROC.value),
            make_notice(source=NoticeSource.TED_EU.value),
        ])
        query, _ = build_search_query(db, sources=["BOSA", "TED"])
        assert query.count() == 2

    def test_single_source_list(self, db):
        from app.services.search_service import build_search_query

        seed_notices(db, [
            make_notice(source=NoticeSource.BOSA_EPROC.value),
            make_notice(source=NoticeSource.TED_EU.value),
        ])
        query, _ = build_search_query(db, sources=["TED"])
        assert query.count() == 1
