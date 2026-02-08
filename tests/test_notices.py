"""Tests for notice endpoints. Use DATABASE_URL from conftest (test.db)."""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, Base, SessionLocal
from app.models.notice import Notice

# Create tables for tests
@pytest.fixture(scope="function")
def db_setup():
    """Create test database tables."""
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("test.db"):
        try:
            os.remove("test.db")
        except PermissionError:
            pass


@pytest.fixture
def client(db_setup):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def notices_ted_and_bosa(db_setup):
    """Insert one TED and one BOSA notice for source-filter tests."""
    db = SessionLocal()
    try:
        db.query(Notice).delete()
        db.add(
            Notice(
                source="TED_EU",
                source_id="ted-1",
                publication_workspace_id="ws-ted-1",
                title="TED notice",
                url="https://ted.europa.eu/1",
            )
        )
        db.add(
            Notice(
                source="BOSA_EPROC",
                source_id="bosa-1",
                publication_workspace_id="ws-bosa-1",
                title="BOSA notice",
                url="https://bosa.be/1",
            )
        )
        db.commit()
        yield
    finally:
        db.close()


def test_list_notices_empty(client):
    """Test listing notices when database is empty."""
    response = client.get("/api/notices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 0
    assert "page" in data
    assert "page_size" in data
    assert "total" in data


def test_list_notices_with_params(client):
    """Test listing notices with query parameters."""
    response = client.get(
        "/api/notices",
        params={
            "page": 1,
            "page_size": 10,
            "q": "test",
            "country": "BE",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "page" in data
    assert "page_size" in data
    assert "total" in data


def test_list_notices_sources_filter(client, notices_ted_and_bosa):
    """Test filtering notices by sources (TED, BOSA). No param returns all."""
    # No sources param: return all
    r_all = client.get("/api/notices", params={"page_size": 10})
    assert r_all.status_code == 200
    assert r_all.json()["total"] == 2
    assert len(r_all.json()["items"]) == 2

    # sources=TED: only TED_EU
    r_ted = client.get("/api/notices", params={"page_size": 10, "sources": "TED"})
    assert r_ted.status_code == 200
    assert r_ted.json()["total"] == 1
    assert r_ted.json()["items"][0]["source"] == "TED_EU"

    # sources=BOSA: only BOSA_EPROC
    r_bosa = client.get("/api/notices", params={"page_size": 10, "sources": "BOSA"})
    assert r_bosa.status_code == 200
    assert r_bosa.json()["total"] == 1
    assert r_bosa.json()["items"][0]["source"] == "BOSA_EPROC"

    # sources=TED,BOSA: both
    r_both = client.get("/api/notices", params={"page_size": 10, "sources": "TED,BOSA"})
    assert r_both.status_code == 200
    assert r_both.json()["total"] == 2
