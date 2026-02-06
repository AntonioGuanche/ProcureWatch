"""Tests for .env loading and auto-discovery."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Set test database URL before importing app
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_env.db"

from app.utils.env import load_env_if_present


def test_load_env_if_present_with_dotenv():
    """Test that load_env_if_present loads .env when dotenv is available."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        env_file = f.name
        f.write("TEST_VAR_FROM_ENV=test_value_123\n")
        f.write("ANOTHER_VAR=another_value\n")
    
    try:
        # Clear the vars if they exist
        if "TEST_VAR_FROM_ENV" in os.environ:
            del os.environ["TEST_VAR_FROM_ENV"]
        if "ANOTHER_VAR" in os.environ:
            del os.environ["ANOTHER_VAR"]
        
        # Load .env
        result = load_env_if_present(env_file)
        
        # Should have loaded
        assert result is True
        assert os.environ.get("TEST_VAR_FROM_ENV") == "test_value_123"
        assert os.environ.get("ANOTHER_VAR") == "another_value"
        
        # Cleanup
        del os.environ["TEST_VAR_FROM_ENV"]
        del os.environ["ANOTHER_VAR"]
    finally:
        Path(env_file).unlink(missing_ok=True)


def test_load_env_if_present_no_dotenv():
    """Test that load_env_if_present doesn't crash when dotenv is missing."""
    with patch.dict("sys.modules", {"dotenv": None}):
        # Should not crash, just return False
        result = load_env_if_present(".env")
        assert result is False


def test_load_env_if_present_nonexistent_file():
    """Test that load_env_if_present handles nonexistent .env gracefully."""
    result = load_env_if_present("/nonexistent/path/.env")
    assert result is False


def test_load_env_if_present_override_false():
    """Test that load_env_if_present doesn't override existing env vars."""
    os.environ["EXISTING_VAR"] = "original_value"
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        env_file = f.name
        f.write("EXISTING_VAR=should_not_override\n")
    
    try:
        load_env_if_present(env_file)
        # Should keep original value (override=False)
        assert os.environ.get("EXISTING_VAR") == "original_value"
    finally:
        Path(env_file).unlink(missing_ok=True)
        if "EXISTING_VAR" in os.environ:
            del os.environ["EXISTING_VAR"]


def test_sync_bosa_auto_discovers_on_missing_endpoints():
    """Test that sync_bosa auto-runs discovery when endpoints not confirmed."""
    from connectors.eprocurement.openapi_discovery import cache_path
    
    # Remove cache if it exists
    cache_file = cache_path()
    cache_file.unlink(missing_ok=True)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create unconfirmed cache (no "confirmed" flag)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "search_publications": {"method": "GET", "path": "/test"},
                "updated_at": "2024-01-01T00:00:00Z",
            },
            f,
        )
    
    try:
        # Import sync_bosa's helper
        from ingest.sync_bosa import _endpoints_confirmed
        
        # Should return False (not confirmed)
        assert _endpoints_confirmed() is False
        
        # Now create confirmed cache
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "confirmed": True,
                    "search_publications": {"method": "GET", "path": "/test"},
                    "updated_at": "2024-01-01T00:00:00Z",
                },
                f,
            )
        
        # Should return True (confirmed)
        assert _endpoints_confirmed() is True
    finally:
        cache_file.unlink(missing_ok=True)


def test_endpoints_cache_confirmed_flag():
    """Test that discovery writes confirmed flag and client reads it."""
    from connectors.eprocurement.openapi_discovery import cache_path, load_or_discover_endpoints
    
    cache_file = cache_path()
    cache_file.unlink(missing_ok=True)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Mock the discovery to avoid network calls
        with patch("connectors.eprocurement.openapi_discovery.download_swagger") as mock_download:
            mock_download.return_value = {
                "paths": {
                    "/search/publications": {
                        "get": {
                            "operationId": "searchPublications",
                            "summary": "Search publications",
                            "parameters": [
                                {"name": "terms", "in": "query"},
                                {"name": "page", "in": "query"},
                                {"name": "pageSize", "in": "query"},
                            ],
                        }
                    }
                }
            }
            
            # Run discovery with confirmed=True
            endpoints = load_or_discover_endpoints(force=True, confirmed=True)
            
            # Check cache was written with confirmed flag
            assert cache_file.exists()
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data.get("confirmed") is True
            
            # Check that loading from cache respects confirmed flag
            endpoints2 = load_or_discover_endpoints(force=False)
            assert endpoints2 is not None
    finally:
        cache_file.unlink(missing_ok=True)
