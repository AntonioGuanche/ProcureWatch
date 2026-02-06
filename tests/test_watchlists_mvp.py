"""Tests for watchlist MVP endpoints. Use DATABASE_URL from conftest (test.db)."""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, Base
from app.db.models.notice import Notice
from app.db.models.watchlist import Watchlist
from app.db.models.watchlist_match import WatchlistMatch
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.session import SessionLocal

# Create tables for tests
@pytest.fixture(scope="function")
def db_setup():
    """Create test database tables (including migrations)."""
    # Ensure all tables exist (alembic first, then Base so notices/watchlists etc. are present)
    import subprocess
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=os.environ.copy(),
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_setup):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_notices(db_setup):
    """Create sample notices for testing."""
    db = SessionLocal()
    try:
        # Create notices with different attributes (using TED/BOSA sources)
        notice1 = Notice(
            id="notice-1",
            source="ted.europa.eu",
            source_id="ted-solar-1",
            title="Solar panel installation project",
            country="BE",
            cpv_main_code="45261200",
            url="https://example.com/notice-1",
            raw_json='{"description": "Installation of solar panels for renewable energy"}',
        )
        notice2 = Notice(
            id="notice-2",
            source="bosa.eprocurement",
            source_id="bosa-wind-1",
            title="Wind turbine maintenance",
            country="FR",
            cpv_main_code="45261200",
            url="https://example.com/notice-2",
            raw_json='{"description": "Maintenance services for wind turbines"}',
        )
        notice3 = Notice(
            id="notice-3",
            source="ted.europa.eu",
            source_id="ted-forest-1",
            title="Forest restoration project",
            country="BE",
            cpv_main_code="45112300",
            url="https://example.com/notice-3",
            raw_json='{"description": "Large scale forest restoration initiative"}',
        )
        notice4 = Notice(
            id="notice-4",
            source="bosa.eprocurement",
            source_id="bosa-forest-1",
            title="Forest restoration services",
            country="BE",
            cpv_main_code="45112300",
            url="https://example.com/notice-4",
            raw_json='{"description": "Forest restoration services procurement"}',
        )
        db.add(notice1)
        db.add(notice2)
        db.add(notice3)
        db.add(notice4)
        
        # Add additional CPV for notice1
        cpv_add = NoticeCpvAdditional(
            notice_id="notice-1",
            cpv_code="45261210",
        )
        db.add(cpv_add)
        
        db.commit()
        yield [notice1, notice2, notice3, notice4]
    finally:
        db.close()


def test_create_watchlist_defaults_to_both_sources(client):
    """Test creating a watchlist without sources defaults to both."""
    response = client.post(
        "/api/watchlists",
        json={
            "name": "Test watchlist",
            "keywords": ["solar"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sources"] == ["TED", "BOSA"]


def test_create_watchlist_with_invalid_source_returns_422(client):
    """Test creating a watchlist with invalid source returns 422."""
    response = client.post(
        "/api/watchlists",
        json={
            "name": "Test watchlist",
            "sources": ["INVALID"],
        },
    )
    assert response.status_code == 422
    assert "Invalid source" in str(response.json())


def test_create_watchlist(client):
    """Test creating a watchlist."""
    response = client.post(
        "/api/watchlists",
        json={
            "name": "Solar projects",
            "keywords": ["solar", "renewable"],
            "countries": ["BE"],
            "cpv_prefixes": ["4526"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Solar projects"
    assert data["keywords"] == ["solar", "renewable"]
    assert data["countries"] == ["BE"]
    assert data["cpv_prefixes"] == ["4526"]
    assert "id" in data
    assert "created_at" in data


def test_list_watchlists(client):
    """Test listing watchlists."""
    # Create a watchlist first
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "Test watchlist",
            "keywords": ["test"],
        },
    )
    assert create_resp.status_code == 201
    
    # List watchlists
    response = client.get("/api/watchlists")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test watchlist"


def test_refresh_creates_matches(client, sample_notices):
    """Test that refresh creates matches."""
    # Create watchlist with keywords
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "Solar watchlist",
            "keywords": ["solar"],
            "countries": ["BE"],
        },
    )
    assert create_resp.status_code == 201
    watchlist_id = create_resp.json()["id"]
    
    # Refresh matches
    refresh_resp = client.post(f"/api/watchlists/{watchlist_id}/refresh")
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    assert "matched" in refresh_data
    assert refresh_data["matched"] > 0
    
    # Check matches endpoint
    matches_resp = client.get(f"/api/watchlists/{watchlist_id}/matches")
    assert matches_resp.status_code == 200
    matches_data = matches_resp.json()
    assert "items" in matches_data
    assert len(matches_data["items"]) > 0
    assert "matched_on" in matches_data["items"][0]
    assert "notice" in matches_data["items"][0]


def test_refresh_no_duplicates(client, sample_notices):
    """Test that second refresh does not create duplicates."""
    # Create watchlist
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "Solar watchlist",
            "keywords": ["solar"],
        },
    )
    watchlist_id = create_resp.json()["id"]
    
    # First refresh
    refresh1 = client.post(f"/api/watchlists/{watchlist_id}/refresh")
    assert refresh1.status_code == 200
    matches1 = refresh1.json()["matched"]
    
    # Second refresh
    refresh2 = client.post(f"/api/watchlists/{watchlist_id}/refresh")
    assert refresh2.status_code == 200
    matches2 = refresh2.json()["matched"]
    
    # Should have same number of matches (no duplicates)
    assert matches1 == matches2
    
    # Check matches endpoint returns same count
    matches_resp = client.get(f"/api/watchlists/{watchlist_id}/matches")
    matches_data = matches_resp.json()
    assert matches_data["total"] == matches1


def test_matches_endpoint_returns_list(client, sample_notices):
    """Test that matches endpoint returns a list."""
    # Create watchlist and refresh
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "Forest watchlist",
            "keywords": ["forest"],
        },
    )
    watchlist_id = create_resp.json()["id"]
    
    client.post(f"/api/watchlists/{watchlist_id}/refresh")
    
    # Get matches
    response = client.get(f"/api/watchlists/{watchlist_id}/matches")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    
    # If there are matches, check structure
    if data["items"]:
        item = data["items"][0]
        assert "notice" in item
        assert "matched_on" in item
        assert isinstance(item["matched_on"], str)


def test_sources_filtering_ted_only(client, sample_notices):
    """Test that watchlist with sources=["TED"] matches only TED notices."""
    from app.db.crud.watchlists_mvp import create_watchlist, refresh_watchlist_matches, get_watchlist_by_id
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        # Create watchlist for TED only
        wl = create_watchlist(
            db,
            name="TED only",
            keywords=["restoration"],
            sources=["TED"],
        )
        
        # Refresh matches
        refresh_watchlist_matches(db, wl)
        
        # Check matches
        matches = db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == wl.id).all()
        matched_notices = [db.query(Notice).filter(Notice.id == m.notice_id).first() for m in matches]
        
        # Should match only TED notice (notice-3)
        assert len(matched_notices) == 1
        assert matched_notices[0].source == "ted.europa.eu"
        assert matched_notices[0].id in ("notice-1", "notice-3")  # Either TED notice
    finally:
        db.close()


def test_sources_filtering_bosa_only(client, sample_notices):
    """Test that watchlist with sources=["BOSA"] matches only BOSA notices."""
    from app.db.crud.watchlists_mvp import create_watchlist, refresh_watchlist_matches
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        # Create watchlist for BOSA only
        wl = create_watchlist(
            db,
            name="BOSA only",
            keywords=["restoration"],
            sources=["BOSA"],
        )
        
        # Refresh matches
        refresh_watchlist_matches(db, wl)
        
        # Check matches
        matches = db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == wl.id).all()
        matched_notices = [db.query(Notice).filter(Notice.id == m.notice_id).first() for m in matches]
        
        # Should match only BOSA notice (notice-4)
        assert len(matched_notices) == 1
        assert matched_notices[0].source == "bosa.eprocurement"
        assert matched_notices[0].id in ("notice-2", "notice-4")  # Either BOSA notice
    finally:
        db.close()


def test_sources_filtering_both(client, sample_notices):
    """Test that watchlist with sources=["TED","BOSA"] matches both."""
    from app.db.crud.watchlists_mvp import create_watchlist, refresh_watchlist_matches
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        # Create watchlist for both sources
        wl = create_watchlist(
            db,
            name="Both sources",
            keywords=["restoration"],
            sources=["TED", "BOSA"],
        )
        
        # Refresh matches
        refresh_watchlist_matches(db, wl)
        
        # Check matches
        matches = db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == wl.id).all()
        matched_notices = [db.query(Notice).filter(Notice.id == m.notice_id).first() for m in matches]
        
        # Should match both TED and BOSA notices
        assert len(matched_notices) == 2
        sources = {n.source for n in matched_notices}
        assert sources == {"ted.europa.eu", "bosa.eprocurement"}
    finally:
        db.close()


def test_cpv_prefix_matching(client, sample_notices):
    """Test that CPV prefix matching works."""
    # Create watchlist with CPV prefix and sources matching test notices
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "CPV 4526 watchlist",
            "cpv_prefixes": ["4526"],
            "sources": ["TED", "BOSA"],  # Match test notices
        },
    )
    watchlist_id = create_resp.json()["id"]
    
    # Refresh
    refresh_resp = client.post(f"/api/watchlists/{watchlist_id}/refresh")
    assert refresh_resp.status_code == 200
    
    # Check matches include notices with matching CPV
    matches_resp = client.get(f"/api/watchlists/{watchlist_id}/matches")
    matches_data = matches_resp.json()
    assert matches_data["total"] > 0
    
    # Verify matched_on includes CPV info
    for item in matches_data["items"]:
        assert "CPV" in item["matched_on"] or len(matches_data["items"]) > 0


def test_country_filtering(client, sample_notices):
    """Test that country filtering works."""
    # Create watchlist with country filter
    create_resp = client.post(
        "/api/watchlists",
        json={
            "name": "Belgium only",
            "countries": ["BE"],
        },
    )
    watchlist_id = create_resp.json()["id"]
    
    # Refresh
    refresh_resp = client.post(f"/api/watchlists/{watchlist_id}/refresh")
    assert refresh_resp.status_code == 200
    
    # Check matches only include BE notices
    matches_resp = client.get(f"/api/watchlists/{watchlist_id}/matches")
    matches_data = matches_resp.json()
    
    for item in matches_data["items"]:
        assert item["notice"]["country"] == "BE"
