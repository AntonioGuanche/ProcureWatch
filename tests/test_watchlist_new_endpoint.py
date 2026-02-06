"""API tests for GET /api/watchlists/{id}/new (new since last_notified_at / last_refresh_at).

NOTE: These tests are for the OLD watchlist API endpoints.
The MVP watchlist API uses different endpoints.
These tests are skipped as they test deprecated functionality.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_watchlist_new.db"

import pytest

# Skip all tests in this file - they test deprecated watchlist API
pytestmark = pytest.mark.skip(reason="Old watchlist API tests - MVP uses new endpoints")

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, SessionLocal
from app.db.base import Base
from app.db.models.notice import Notice
from app.db.models.watchlist import Watchlist


@pytest.fixture(scope="function")
def db_setup():
    """Create test database tables; drop after test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_setup):
    """Test client."""
    return TestClient(app)


def test_new_empty_no_cutoff(client: TestClient):
    """GET /api/watchlists/{id}/new returns empty when no last_notified_at or last_refresh_at (first run)."""
    create = client.post("/api/watchlists", json={"name": "No Cutoff", "country": "BE"})
    assert create.status_code == 201
    wl_id = create.json()["id"]
    resp = client.get(f"/api/watchlists/{wl_id}/new?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert data["items"] == []


def test_new_with_cutoff_returns_matching(client: TestClient, db_setup):
    """GET /api/watchlists/{id}/new returns notices with first_seen_at > cutoff (last_refresh_at)."""
    db = SessionLocal()
    try:
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        wl = Watchlist(
            name="With Cutoff",
            is_enabled=True,
            term="Build",
            country="BE",
            last_refresh_at=past,
        )
        db.add(wl)
        db.commit()
        db.refresh(wl)
        wl_id = wl.id

        n = Notice(
            source="publicprocurement.be",
            source_id="new-1",
            title="Build works",
            country="BE",
            url="https://example.com/1",
        )
        db.add(n)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/watchlists/{wl_id}/new?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["title"] == "Build works"


def test_new_404(client: TestClient):
    """GET /api/watchlists/{id}/new returns 404 for unknown watchlist."""
    resp = client.get("/api/watchlists/00000000-0000-0000-0000-000000000000/new?page=1&page_size=25")
    assert resp.status_code == 404


def test_new_pagination_shape(client: TestClient, db_setup):
    """GET /api/watchlists/{id}/new returns NoticeListResponse shape (total, page, page_size, items)."""
    db = SessionLocal()
    try:
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        wl = Watchlist(name="Shape", is_enabled=True, country="BE", last_refresh_at=past)
        db.add(wl)
        db.commit()
        db.refresh(wl)
        wl_id = wl.id
    finally:
        db.close()

    resp = client.get(f"/api/watchlists/{wl_id}/new?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert "items" in data
    assert isinstance(data["items"], list)
