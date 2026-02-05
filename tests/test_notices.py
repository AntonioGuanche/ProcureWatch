"""Tests for notice endpoints."""
import os

# Set test database URL before importing app
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, Base

# Create tables for tests
@pytest.fixture(scope="function")
def db_setup():
    """Create test database tables."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    # Clean up test database file
    if os.path.exists("test.db"):
        os.remove("test.db")


@pytest.fixture
def client(db_setup):
    """Create test client."""
    return TestClient(app)


def test_list_notices_empty(client):
    """Test listing notices when database is empty."""
    response = client.get("/api/notices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_list_notices_with_params(client):
    """Test listing notices with query parameters."""
    response = client.get(
        "/api/notices",
        params={
            "limit": 10,
            "offset": 0,
            "q": "test",
            "country": "BE",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
