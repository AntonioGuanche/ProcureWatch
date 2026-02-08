"""Tests for filter endpoints."""
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
    engine.dispose()
    if os.path.exists("test.db"):
        try:
            os.remove("test.db")
        except PermissionError:
            pass


@pytest.fixture
def client(db_setup):
    """Create test client."""
    return TestClient(app)


def test_create_filter(client):
    """Test creating a filter."""
    response = client.post(
        "/api/filters",
        json={
            "name": "Test Filter",
            "keywords": "construction, building",
            "cpv_prefixes": "45,48",
            "countries": "BE,FR",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Filter"
    assert data["keywords"] == "construction, building"
    assert "id" in data
    assert "created_at" in data


def test_list_filters(client):
    """Test listing filters."""
    # Create a filter first
    client.post(
        "/api/filters",
        json={"name": "Filter 1", "keywords": "test"},
    )

    response = client.get("/api/filters")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_filter(client):
    """Test getting a filter by ID."""
    # Create a filter
    create_response = client.post(
        "/api/filters",
        json={"name": "Test Filter", "keywords": "test"},
    )
    filter_id = create_response.json()["id"]

    # Get the filter
    response = client.get(f"/api/filters/{filter_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == filter_id
    assert data["name"] == "Test Filter"


def test_update_filter(client):
    """Test updating a filter."""
    # Create a filter
    create_response = client.post(
        "/api/filters",
        json={"name": "Original Name", "keywords": "old"},
    )
    filter_id = create_response.json()["id"]

    # Update the filter
    response = client.patch(
        f"/api/filters/{filter_id}",
        json={"name": "Updated Name", "keywords": "new"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["keywords"] == "new"


def test_delete_filter(client):
    """Test deleting a filter."""
    # Create a filter
    create_response = client.post(
        "/api/filters",
        json={"name": "To Delete", "keywords": "test"},
    )
    filter_id = create_response.json()["id"]

    # Delete the filter
    response = client.delete(f"/api/filters/{filter_id}")
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(f"/api/filters/{filter_id}")
    assert get_response.status_code == 404
