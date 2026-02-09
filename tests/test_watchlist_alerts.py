"""Tests for Phase 7: watchlist alerts (CRUD, matching, email)."""
import json
import uuid
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource
from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch


@pytest.fixture()
def db():
    """In-memory SQLite session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _notice(**kwargs) -> ProcurementNotice:
    defaults = {
        "id": str(uuid.uuid4()),
        "source_id": f"src-{uuid.uuid4().hex[:8]}",
        "source": NoticeSource.BOSA_EPROC.value,
        "publication_workspace_id": f"ws-{uuid.uuid4().hex[:8]}",
        "title": "Default notice",
        "publication_date": date(2024, 6, 1),
        "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return ProcurementNotice(**defaults)


def _watchlist(**kwargs) -> Watchlist:
    defaults = {
        "id": str(uuid.uuid4()),
        "name": "Test watchlist",
        "enabled": True,
    }
    defaults.update(kwargs)
    return Watchlist(**defaults)


# ── CRUD tests ──


def test_create_watchlist_with_new_fields(db):
    """Create watchlist with enabled, notify_email, nuts_prefixes."""
    from app.db.crud.watchlists_mvp import create_watchlist, _parse_array

    wl = create_watchlist(
        db,
        name="Construction BE",
        keywords=["construction", "bâtiment"],
        cpv_prefixes=["45"],
        nuts_prefixes=["BE1", "BE2"],
        sources=["BOSA"],
        enabled=True,
        notify_email="test@example.com",
    )
    assert wl.name == "Construction BE"
    assert wl.enabled is True
    assert wl.notify_email == "test@example.com"
    assert _parse_array(wl.nuts_prefixes) == ["BE1", "BE2"]
    assert _parse_array(wl.keywords) == ["construction", "bâtiment"]


def test_update_watchlist_toggle_enabled(db):
    """Update watchlist: disable and change email."""
    from app.db.crud.watchlists_mvp import create_watchlist, update_watchlist

    wl = create_watchlist(db, name="Test", enabled=True, notify_email="a@b.com")
    updated = update_watchlist(db, wl.id, enabled=False, notify_email="new@b.com")
    assert updated.enabled is False
    assert updated.notify_email == "new@b.com"


def test_delete_watchlist_cascades(db):
    """Delete watchlist also removes matches."""
    from app.db.crud.watchlists_mvp import create_watchlist, delete_watchlist

    wl = create_watchlist(db, name="To delete")
    n = _notice()
    db.add(n)
    db.commit()

    match = WatchlistMatch(watchlist_id=wl.id, notice_id=n.id, matched_on="test")
    db.add(match)
    db.commit()

    assert db.query(WatchlistMatch).count() == 1
    delete_watchlist(db, wl.id)
    assert db.query(WatchlistMatch).count() == 0


# ── Matcher tests ──


def test_matcher_keyword_match(db):
    """Matcher finds notices containing watchlist keywords."""
    from app.services.watchlist_matcher import match_watchlist

    n1 = _notice(title="Construction de route", created_at=datetime.now(timezone.utc))
    n2 = _notice(title="Fournitures papier", created_at=datetime.now(timezone.utc))
    db.add_all([n1, n2])
    db.commit()

    wl = _watchlist(keywords="construction")
    db.add(wl)
    db.commit()

    # Match from the beginning (no since cutoff)
    new = match_watchlist(db, wl, since=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert len(new) == 1
    assert new[0].id == n1.id

    # Match stored
    assert db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == wl.id).count() == 1


def test_matcher_cpv_match(db):
    """Matcher filters on CPV prefix."""
    from app.services.watchlist_matcher import match_watchlist

    n1 = _notice(cpv_main_code="45000000-7", created_at=datetime.now(timezone.utc))
    n2 = _notice(cpv_main_code="71000000-8", created_at=datetime.now(timezone.utc))
    db.add_all([n1, n2])
    db.commit()

    wl = _watchlist(cpv_prefixes="45")
    db.add(wl)
    db.commit()

    new = match_watchlist(db, wl, since=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert len(new) == 1
    assert new[0].cpv_main_code == "45000000-7"


def test_matcher_dedup(db):
    """Running matcher twice doesn't duplicate matches."""
    from app.services.watchlist_matcher import match_watchlist

    n1 = _notice(title="Construction", created_at=datetime.now(timezone.utc))
    db.add(n1)
    db.commit()

    wl = _watchlist(keywords="construction")
    db.add(wl)
    db.commit()

    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    first = match_watchlist(db, wl, since=since)
    assert len(first) == 1

    # Run again — should find 0 new (already matched + last_refresh_at updated)
    second = match_watchlist(db, wl)
    assert len(second) == 0

    # Total matches still 1
    assert db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == wl.id).count() == 1


def test_matcher_source_filter(db):
    """Matcher respects source filter."""
    from app.services.watchlist_matcher import match_watchlist

    n_bosa = _notice(source=NoticeSource.BOSA_EPROC.value, title="Route BOSA", created_at=datetime.now(timezone.utc))
    n_ted = _notice(source=NoticeSource.TED_EU.value, title="Route TED", created_at=datetime.now(timezone.utc))
    db.add_all([n_bosa, n_ted])
    db.commit()

    wl = _watchlist(keywords="route", sources=json.dumps(["BOSA"]))
    db.add(wl)
    db.commit()

    new = match_watchlist(db, wl, since=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert len(new) == 1
    assert new[0].source == NoticeSource.BOSA_EPROC.value


# ── Email notification tests ──


def test_matcher_sends_email(db):
    """Matcher sends email when notify_email is set and matches found."""
    from app.services.watchlist_matcher import run_watchlist_matcher

    n1 = _notice(title="Construction pont", created_at=datetime.now(timezone.utc))
    db.add(n1)
    db.commit()

    wl = _watchlist(keywords="construction", enabled=True, notify_email="user@test.com")
    db.add(wl)
    db.commit()

    with patch("app.services.watchlist_matcher.send_watchlist_notification") as mock_send:
        result = run_watchlist_matcher(db)

    assert result["watchlists_processed"] == 1
    assert result["total_new_matches"] == 1
    assert result["emails_sent"] == 1
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[1]["to_address"] == "user@test.com"


def test_matcher_skips_disabled(db):
    """Matcher skips disabled watchlists."""
    from app.services.watchlist_matcher import run_watchlist_matcher

    n1 = _notice(title="Construction", created_at=datetime.now(timezone.utc))
    db.add(n1)
    db.commit()

    wl = _watchlist(keywords="construction", enabled=False, notify_email="user@test.com")
    db.add(wl)
    db.commit()

    with patch("app.services.watchlist_matcher.send_watchlist_notification") as mock_send:
        result = run_watchlist_matcher(db)

    assert result["watchlists_processed"] == 0
    mock_send.assert_not_called()


def test_matcher_no_email_when_no_matches(db):
    """No email sent when no new matches."""
    from app.services.watchlist_matcher import run_watchlist_matcher

    wl = _watchlist(keywords="xyznonexistent", enabled=True, notify_email="user@test.com")
    db.add(wl)
    db.commit()

    with patch("app.services.watchlist_matcher.send_watchlist_notification") as mock_send:
        result = run_watchlist_matcher(db)

    assert result["total_new_matches"] == 0
    mock_send.assert_not_called()


# ── run_watchlist_matcher summary ──


def test_run_matcher_multiple_watchlists(db):
    """Matcher processes multiple enabled watchlists."""
    from app.services.watchlist_matcher import run_watchlist_matcher

    n1 = _notice(title="Construction route", cpv_main_code="45000000-7", created_at=datetime.now(timezone.utc))
    n2 = _notice(title="Fournitures IT", cpv_main_code="72000000-5", created_at=datetime.now(timezone.utc))
    db.add_all([n1, n2])
    db.commit()

    wl1 = _watchlist(name="Construction", keywords="construction", enabled=True)
    wl2 = _watchlist(name="IT", cpv_prefixes="72", enabled=True)
    db.add_all([wl1, wl2])
    db.commit()

    with patch("app.services.watchlist_matcher.send_watchlist_notification"):
        result = run_watchlist_matcher(db)

    assert result["watchlists_processed"] == 2
    assert result["total_new_matches"] == 2
    details = {d["watchlist_name"]: d["new_matches"] for d in result["details"]}
    assert details["Construction"] == 1
    assert details["IT"] == 1
