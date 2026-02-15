"""Tests for main application routes."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    """Test root endpoint serves SPA or API fallback."""
    response = client.get("/")
    assert response.status_code == 200
    # If frontend is built, root serves index.html (HTML, not JSON)
    # If not, it returns JSON {"name": ..., "status": "running"}
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text
    else:
        data = response.json()
        assert data["name"] == "procurewatch-api"
        assert data["status"] == "running"


def test_health_ok(monkeypatch) -> None:
    """Test health endpoint when DB is available."""
    # Mock check_db_connection to return True
    from app.db import session
    original_check = session.check_db_connection
    
    def mock_check_ok() -> bool:
        return True
    
    monkeypatch.setattr(session, "check_db_connection", mock_check_ok)
    
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_health_degraded(monkeypatch) -> None:
    """Test health endpoint when DB is unavailable."""
    # Mock check_db_connection to return False - patch where it's imported in health.py
    from app.api.routes import health
    
    def mock_check_fail() -> bool:
        return False
    
    monkeypatch.setattr(health, "check_db_connection", mock_check_fail)
    
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["status"] == "degraded"
    assert data["detail"]["db"] == "error"
