"""Unit tests for watchlist matching logic (no network).

NOTE: These tests are for the OLD watchlist schema (term, cpv_prefix, etc.).
The MVP watchlist schema uses keywords[], countries[], cpv_prefixes[] arrays.
These tests are skipped as they test deprecated functionality.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_watchlist.db"

import pytest

# Skip all tests in this file - they test deprecated watchlist schema
pytestmark = pytest.mark.skip(reason="Old watchlist schema tests - MVP uses new array-based schema")

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.models.notice import Notice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.models.watchlist import Watchlist
from app.db.crud.watchlists import list_notices_for_watchlist


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(db_schema):
    """Fresh session per test; clear watchlist/notice data before each test."""
    session = SessionLocal()
    # Clear so each test starts with empty notice/watchlist data
    session.query(NoticeCpvAdditional).delete()
    session.query(Notice).delete()
    session.query(Watchlist).delete()
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _add_notice(
    db: Session,
    source_id: str,
    title: str,
    buyer_name: str | None = None,
    country: str | None = "BE",
    language: str | None = "FR",
    cpv_main_code: str | None = "45000000",
    procedure_type: str | None = "OPEN",
) -> Notice:
    n = Notice(
        source="publicprocurement.be",
        source_id=source_id,
        title=title,
        buyer_name=buyer_name,
        country=country,
        language=language,
        cpv_main_code=cpv_main_code,
        cpv=cpv_main_code,
        procedure_type=procedure_type,
        url="https://example.com/1",
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _add_cpv_additional(db: Session, notice_id: str, cpv_code: str) -> None:
    db.add(NoticeCpvAdditional(notice_id=notice_id, cpv_code=cpv_code))
    db.commit()


def _add_watchlist(
    db: Session,
    name: str = "Test",
    term: str | None = None,
    cpv_prefix: str | None = None,
    buyer_contains: str | None = None,
    procedure_type: str | None = None,
    country: str = "BE",
    language: str | None = None,
) -> Watchlist:
    wl = Watchlist(
        name=name,
        is_enabled=True,
        term=term,
        cpv_prefix=cpv_prefix,
        buyer_contains=buyer_contains,
        procedure_type=procedure_type,
        country=country,
        language=language,
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def test_match_term_only(db: Session):
    """Term filter: case-insensitive contains on title."""
    _add_notice(db, "id1", "Travaux de construction")
    _add_notice(db, "id2", "Maintenance building")
    wl = _add_watchlist(db, term="travaux")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].title == "Travaux de construction"


def test_match_cpv_prefix_main(db: Session):
    """cpv_prefix matches main CPV code (startswith)."""
    _add_notice(db, "id1", "Title A", cpv_main_code="45000000")
    _add_notice(db, "id2", "Title B", cpv_main_code="71000000")
    wl = _add_watchlist(db, cpv_prefix="45")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].cpv_main_code == "45000000"


def test_match_cpv_prefix_additional(db: Session):
    """cpv_prefix matches any additional CPV code (startswith)."""
    n1 = _add_notice(db, "id1", "Title A", cpv_main_code="71000000")
    _add_cpv_additional(db, n1.id, "45000000")
    _add_notice(db, "id2", "Title B", cpv_main_code="71000000")
    wl = _add_watchlist(db, cpv_prefix="45")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].source_id == "id1"


def test_match_buyer_contains(db: Session):
    """buyer_contains: case-insensitive contains on buyer_name; skip if buyer_name null."""
    _add_notice(db, "id1", "Title A", buyer_name="Ville de Bruxelles")
    _add_notice(db, "id2", "Title B", buyer_name=None)
    _add_notice(db, "id3", "Title C", buyer_name="SPF Finances")
    wl = _add_watchlist(db, buyer_contains="bruxelles")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].buyer_name == "Ville de Bruxelles"


def test_match_procedure_type(db: Session):
    """procedure_type: exact match."""
    _add_notice(db, "id1", "Title A", procedure_type="OPEN")
    _add_notice(db, "id2", "Title B", procedure_type="NEG_WO_CALL_24")
    wl = _add_watchlist(db, procedure_type="OPEN")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].procedure_type == "OPEN"


def test_match_country(db: Session):
    """country: exact match."""
    _add_notice(db, "id1", "Title A", country="BE")
    _add_notice(db, "id2", "Title B", country="FR")
    wl = _add_watchlist(db, country="BE")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].country == "BE"


def test_match_language(db: Session):
    """language: exact match if set on notice."""
    _add_notice(db, "id1", "Title A", language="FR")
    _add_notice(db, "id2", "Title B", language="NL")
    wl = _add_watchlist(db, language="FR")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].language == "FR"


def test_match_all_filters_combined(db: Session):
    """All non-null filters must match."""
    n1 = _add_notice(
        db, "id1", "Travaux construction", buyer_name="Ville Bruxelles",
        country="BE", language="FR", cpv_main_code="45000000", procedure_type="OPEN",
    )
    _add_notice(db, "id2", "Travaux other", buyer_name="Other", country="BE", language="FR", cpv_main_code="45000000", procedure_type="OPEN")
    wl = _add_watchlist(db, term="construction", buyer_contains="Bruxelles", country="BE", procedure_type="OPEN")
    notices, total = list_notices_for_watchlist(db, wl, limit=10, offset=0)
    assert total == 1
    assert notices[0].source_id == "id1"


def test_preview_pagination(db: Session):
    """Preview returns correct page and total."""
    for i in range(5):
        _add_notice(db, f"id{i}", f"Title {i}", country="BE")
    wl = _add_watchlist(db, country="BE")
    page1, total = list_notices_for_watchlist(db, wl, limit=2, offset=0)
    assert total == 5
    assert len(page1) == 2
    page2, _ = list_notices_for_watchlist(db, wl, limit=2, offset=2)
    assert len(page2) == 2
