"""Unit tests for watchlist notification selection: first run => no email; second run with new items => email (file mode).

NOTE: These tests are for the OLD watchlist schema and notification system.
The MVP watchlist uses a different schema and matching system.
These tests are skipped as they test deprecated functionality.
"""
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

# Skip all tests in this file - they test deprecated watchlist functionality
pytestmark = pytest.mark.skip(reason="Old watchlist notification tests - MVP uses new schema")

# Force file mode and temp outbox before importing app modules that read config
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_notify.db"
os.environ["EMAIL_MODE"] = "file"


@pytest.fixture(scope="module")
def outbox_dir():
    """Temporary outbox directory for the test module."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture(autouse=True)
def set_outbox_env(outbox_dir):
    """Point EMAIL_OUTBOX_DIR to temp dir for tests that use emailer."""
    os.environ["EMAIL_OUTBOX_DIR"] = str(outbox_dir)
    yield
    if "EMAIL_OUTBOX_DIR" in os.environ:
        del os.environ["EMAIL_OUTBOX_DIR"]


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    from app.db.session import engine
    from app.models.base import Base
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _add_notice(db, source_id: str, title: str, country: str = "BE", created_at: datetime | None = None):
    from app.models.notice import Notice
    n = Notice(
        source="publicprocurement.be",
        source_id=source_id,
        title=title,
        country=country,
        url="https://example.com/1",
    )
    if created_at:
        n.created_at = created_at
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _add_watchlist(db, name: str, term: str | None = None, notify_email: str | None = None, last_refresh_at=None, last_notified_at=None):
    from app.models.watchlist import Watchlist
    wl = Watchlist(
        name=name,
        is_enabled=True,
        term=term,
        country="BE",
        notify_email=notify_email,
        last_refresh_at=last_refresh_at,
        last_notified_at=last_notified_at,
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def _mock_sync_page(*args, **kwargs):
    """No-op sync result to avoid network in tests."""
    return {"fetched": 0, "imported_new": 0, "imported_updated": 0, "errors": 0}


def test_first_run_no_email(db_schema, outbox_dir):
    """First run (last_refresh_at was null): no email sent; outbox stays empty."""
    from app.db.session import SessionLocal
    from ingest.refresh_watchlists import refresh_one_watchlist

    with patch("ingest.refresh_watchlists.run_sync_page", side_effect=_mock_sync_page):
        db = SessionLocal()
        try:
            before = set(outbox_dir.iterdir()) if outbox_dir.exists() else set()
            wl = _add_watchlist(db, "First Run", term="test", notify_email="user@example.com", last_refresh_at=None)
            refresh_one_watchlist(db, wl, max_pages=1, page_size=25)
            after = set(outbox_dir.iterdir()) if outbox_dir.exists() else set()
            new_files = after - before
            assert len(new_files) == 0, "First run must not send email; no new outbox file expected"
        finally:
            db.close()


def test_second_run_with_new_items_email_created(db_schema, outbox_dir):
    """Second refresh with a notice newly seen (first_seen_at after last_notified_at): email created (file mode)."""
    import os
    from app.db.session import SessionLocal
    from ingest.refresh_watchlists import refresh_one_watchlist

    os.environ["EMAIL_OUTBOX_DIR"] = str(outbox_dir)
    with patch("ingest.refresh_watchlists.run_sync_page", side_effect=_mock_sync_page):
        db = SessionLocal()
        try:
            # Cutoff = last_notified_at (preferred) else last_refresh_at; use fixed past so first_seen_at > cutoff
            past = datetime(2000, 1, 1)
            wl = _add_watchlist(
                db, "Second Run", term="NewNotice", notify_email="user@example.com",
                last_refresh_at=past, last_notified_at=past,
            )
            # Notice matches watchlist; first_seen_at will be "now" from DB (newly seen by ProcureWatch)
            _add_notice(db, "new-1", "NewNotice construction", "BE")

            before = set(outbox_dir.iterdir()) if outbox_dir.exists() else set()
            refresh_one_watchlist(db, wl, max_pages=1, page_size=25)
            after = set(outbox_dir.iterdir()) if outbox_dir.exists() else set()
            new_files = after - before
            assert len(new_files) >= 1, "Second run with new notices must write one email file to outbox"
            content = next(iter(new_files)).read_text(encoding="utf-8")
            assert "ProcureWatch" in content
            assert "new notices" in content or "1 new" in content
            assert "user@example.com" in content or "To:" in content
        finally:
            db.close()
