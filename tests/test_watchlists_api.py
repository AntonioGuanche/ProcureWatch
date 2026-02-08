"""API tests for watchlists: CRUD + preview (TestClient + temporary SQLite).

NOTE: These tests are for the OLD watchlist API endpoints.
The MVP watchlist API uses different endpoints and schema.
These tests are skipped as they test deprecated functionality.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_watchlists_api.db"

import pytest

# Skip all tests in this file - they test deprecated watchlist API
pytestmark = pytest.mark.skip(reason="Old watchlist API tests - MVP uses new endpoints")

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, SessionLocal
from app.models.base import Base
from app.models.notice import Notice
from app.models.watchlist import Watchlist


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


def test_create_watchlist(client: TestClient):
    """POST /api/watchlists creates a watchlist."""
    resp = client.post(
        "/api/watchlists",
        json={
            "name": "My Alert",
            "is_enabled": True,
            "term": "travaux",
            "country": "BE",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Alert"
    assert data["term"] == "travaux"
    assert data["country"] == "BE"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_list_watchlists(client: TestClient):
    """GET /api/watchlists returns paginated list."""
    client.post("/api/watchlists", json={"name": "W1", "country": "BE"})
    client.post("/api/watchlists", json={"name": "W2", "country": "BE"})
    resp = client.get("/api/watchlists?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert "items" in data
    assert len(data["items"]) >= 2


def test_get_watchlist(client: TestClient):
    """GET /api/watchlists/{id} returns a watchlist."""
    create = client.post("/api/watchlists", json={"name": "GetMe", "country": "BE"})
    assert create.status_code == 201
    wl_id = create.json()["id"]
    resp = client.get(f"/api/watchlists/{wl_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetMe"


def test_get_watchlist_404(client: TestClient):
    """GET /api/watchlists/{id} returns 404 for unknown id."""
    resp = client.get("/api/watchlists/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_patch_watchlist(client: TestClient):
    """PATCH /api/watchlists/{id} updates a watchlist."""
    create = client.post("/api/watchlists", json={"name": "Original", "country": "BE"})
    wl_id = create.json()["id"]
    resp = client.patch(
        f"/api/watchlists/{wl_id}",
        json={"name": "Updated", "is_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"
    assert resp.json()["is_enabled"] is False


def test_delete_watchlist(client: TestClient):
    """DELETE /api/watchlists/{id} removes watchlist."""
    create = client.post("/api/watchlists", json={"name": "ToDelete", "country": "BE"})
    wl_id = create.json()["id"]
    resp = client.delete(f"/api/watchlists/{wl_id}")
    assert resp.status_code == 204
    get_resp = client.get(f"/api/watchlists/{wl_id}")
    assert get_resp.status_code == 404


def test_preview_empty(client: TestClient):
    """GET /api/watchlists/{id}/preview returns NoticeListResponse shape (empty)."""
    create = client.post("/api/watchlists", json={"name": "Preview", "term": "nonexistent", "country": "BE"})
    wl_id = create.json()["id"]
    resp = client.get(f"/api/watchlists/{wl_id}/preview?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert "items" in data
    assert isinstance(data["items"], list)


def test_preview_with_notices(client: TestClient, db_setup):
    """Preview returns matching notices when DB has notices."""
    # Insert a notice directly so we have data
    db = SessionLocal()
    try:
        from app.models.notice import Notice
        n = Notice(
            source="publicprocurement.be",
            source_id="test-1",
            title="Travaux test",
            country="BE",
            url="https://example.com/1",
        )
        db.add(n)
        db.commit()
    finally:
        db.close()

    create = client.post("/api/watchlists", json={"name": "Travaux", "term": "Travaux", "country": "BE"})
    wl_id = create.json()["id"]
    resp = client.get(f"/api/watchlists/{wl_id}/preview?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["title"] == "Travaux test"


def test_refresh_rate_limit_429(client: TestClient, db_setup):
    """POST /api/watchlists/{id}/refresh returns 429 if last_refresh_at < 10 minutes ago."""
    from datetime import datetime, timezone
    from app.db.crud.watchlists import update_watchlist

    create = client.post("/api/watchlists", json={"name": "RateLimit", "country": "BE"})
    assert create.status_code == 201
    wl_id = create.json()["id"]

    # Set last_refresh_at to now so next refresh is rate-limited
    db = SessionLocal()
    try:
        update_watchlist(db, wl_id, last_refresh_at=datetime.now(timezone.utc))
    finally:
        db.close()

    resp = client.post(f"/api/watchlists/{wl_id}/refresh")
    assert resp.status_code == 429
    assert "rate" in resp.json().get("detail", "").lower() or "10" in resp.json().get("detail", "")
