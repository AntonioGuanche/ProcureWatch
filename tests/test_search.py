"""Tests for search_service (full-text + filters) and facets endpoint."""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource


@pytest.fixture()
def db():
    """In-memory SQLite session with notices table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_notice(**kwargs) -> ProcurementNotice:
    """Factory for ProcurementNotice with sensible defaults."""
    defaults = {
        "id": str(uuid.uuid4()),
        "source_id": f"src-{uuid.uuid4().hex[:8]}",
        "source": NoticeSource.BOSA_EPROC.value,
        "publication_workspace_id": f"ws-{uuid.uuid4().hex[:8]}",
        "title": "Default title",
        "publication_date": date(2024, 1, 15),
    }
    defaults.update(kwargs)
    return ProcurementNotice(**defaults)


def _seed(db, notices: list[ProcurementNotice]):
    for n in notices:
        db.add(n)
    db.commit()


# ── _parse_tsquery tests ──


def test_parse_tsquery_simple():
    from app.services.search_service import _parse_tsquery
    assert _parse_tsquery("construction") == "construction:*"


def test_parse_tsquery_multiple_words():
    from app.services.search_service import _parse_tsquery
    result = _parse_tsquery("travaux publics")
    assert "travaux:*" in result
    assert "publics:*" in result
    assert "&" in result


def test_parse_tsquery_or():
    from app.services.search_service import _parse_tsquery
    result = _parse_tsquery("route OR pont")
    assert "|" in result


def test_parse_tsquery_empty():
    from app.services.search_service import _parse_tsquery
    assert _parse_tsquery("") == ""
    assert _parse_tsquery("   ") == ""


# ── _source_value tests ──


def test_source_value_bosa():
    from app.services.search_service import _source_value
    assert _source_value("BOSA") == "BOSA_EPROC"
    assert _source_value("bosa") == "BOSA_EPROC"


def test_source_value_ted():
    from app.services.search_service import _source_value
    assert _source_value("TED") == "TED_EU"
    assert _source_value("ted_eu") == "TED_EU"


def test_source_value_unknown():
    from app.services.search_service import _source_value
    assert _source_value("unknown") is None


# ── build_search_query (SQLite fallback) ──


def test_search_no_filters(db):
    """No filters → returns all notices."""
    from app.services.search_service import build_search_query

    _seed(db, [_make_notice(title="A"), _make_notice(title="B")])
    query, has_rank = build_search_query(db)
    assert has_rank is False
    assert query.count() == 2


def test_search_keyword_ilike(db):
    """SQLite: keyword search uses ILIKE fallback."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(title="Construction de route"),
        _make_notice(title="Fourniture de papier"),
    ])
    query, _ = build_search_query(db, q="construction")
    assert query.count() == 1
    row = query.first()
    assert "Construction" in row.title


def test_search_cpv_prefix(db):
    """CPV prefix filter matches first N digits."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(cpv_main_code="45000000-7"),
        _make_notice(cpv_main_code="45210000-2"),
        _make_notice(cpv_main_code="71000000-8"),
    ])
    query, _ = build_search_query(db, cpv="45")
    assert query.count() == 2

    query2, _ = build_search_query(db, cpv="4521")
    assert query2.count() == 1


def test_search_source_filter(db):
    """Source filter maps BOSA/TED to enum values."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(source=NoticeSource.BOSA_EPROC.value),
        _make_notice(source=NoticeSource.TED_EU.value),
    ])
    q_bosa, _ = build_search_query(db, source="BOSA")
    assert q_bosa.count() == 1

    q_ted, _ = build_search_query(db, source="TED")
    assert q_ted.count() == 1


def test_search_date_range(db):
    """Date range filters."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(publication_date=date(2024, 1, 1)),
        _make_notice(publication_date=date(2024, 6, 15)),
        _make_notice(publication_date=date(2024, 12, 31)),
    ])
    query, _ = build_search_query(db, date_from=date(2024, 3, 1), date_to=date(2024, 9, 1))
    assert query.count() == 1


def test_search_notice_type_filter(db):
    """Notice type filter."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(notice_type="CONTRACT_NOTICE"),
        _make_notice(notice_type="CONTRACT_AWARD"),
        _make_notice(notice_type="CONTRACT_NOTICE"),
    ])
    query, _ = build_search_query(db, notice_type="CONTRACT_NOTICE")
    assert query.count() == 2


def test_search_combined_filters(db):
    """Multiple filters combine with AND."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(title="Construction pont", source=NoticeSource.BOSA_EPROC.value, cpv_main_code="45000000-7"),
        _make_notice(title="Construction école", source=NoticeSource.TED_EU.value, cpv_main_code="45000000-7"),
        _make_notice(title="Fournitures", source=NoticeSource.BOSA_EPROC.value, cpv_main_code="33000000-0"),
    ])
    query, _ = build_search_query(db, q="construction", source="BOSA", cpv="45")
    assert query.count() == 1
    assert "pont" in query.first().title


def test_search_sort_date_asc(db):
    """Sort by date ascending."""
    from app.services.search_service import build_search_query

    _seed(db, [
        _make_notice(title="C", publication_date=date(2024, 12, 1)),
        _make_notice(title="A", publication_date=date(2024, 1, 1)),
        _make_notice(title="B", publication_date=date(2024, 6, 1)),
    ])
    query, _ = build_search_query(db, sort="date_asc")
    rows = query.all()
    assert rows[0].title == "A"
    assert rows[2].title == "C"


# ── get_facets tests ──


def test_facets_basic(db):
    """Facets returns expected structure."""
    from app.services.search_service import get_facets

    _seed(db, [
        _make_notice(source=NoticeSource.BOSA_EPROC.value, cpv_main_code="45000000-7", notice_type="CONTRACT_NOTICE"),
        _make_notice(source=NoticeSource.BOSA_EPROC.value, cpv_main_code="45210000-2", notice_type="CONTRACT_NOTICE"),
        _make_notice(source=NoticeSource.TED_EU.value, cpv_main_code="71000000-8", notice_type="CONTRACT_AWARD"),
    ])

    facets = get_facets(db)

    assert facets["total_notices"] == 3
    assert len(facets["sources"]) == 2
    assert any(s["value"] == "BOSA_EPROC" and s["count"] == 2 for s in facets["sources"])
    assert any(s["value"] == "TED_EU" and s["count"] == 1 for s in facets["sources"])

    # CPV divisions
    assert len(facets["top_cpv_divisions"]) >= 2
    codes = {c["code"] for c in facets["top_cpv_divisions"]}
    assert "45" in codes
    assert "71" in codes

    # Notice types
    assert len(facets["notice_types"]) == 2

    # Date range
    assert facets["date_range"]["min"] is not None
    assert facets["date_range"]["max"] is not None


# ── _safe_date tests ──


def test_safe_date():
    """Helper parses dates and returns None on invalid."""
    # Import from notices.py
    from app.api.routes.notices import _safe_date

    assert _safe_date("2024-01-15") == date(2024, 1, 15)
    assert _safe_date("invalid") is None
    assert _safe_date(None) is None
    assert _safe_date("") is None
