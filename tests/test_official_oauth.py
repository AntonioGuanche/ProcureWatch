"""Tests for official e-Procurement OAuth client (mocked, no network)."""
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.official_client import (
    EProcurementCredentialsError,
    EProcurementEndpointNotConfiguredError,
    OfficialEProcurementClient,
)


def test_get_access_token_requires_credentials() -> None:
    """Missing credentials must raise EProcurementCredentialsError."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id=None,
        client_secret=None,
    )
    with pytest.raises(EProcurementCredentialsError) as exc_info:
        client.get_access_token()
    assert "EPROC_CLIENT_ID" in str(exc_info.value) or "credentials" in str(exc_info.value).lower()


def test_get_access_token_retrieves_token() -> None:
    """Token retrieval returns access_token and caches it."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "test-token-123",
            "expires_in": 3600,
        }

        client = OfficialEProcurementClient(
            token_url="https://example.com/token",
            client_id="client_id",
            client_secret="client_secret",
        )
        token = client.get_access_token()

        assert token == "test-token-123"
        mock_post.assert_called_once()
        call_data = mock_post.call_args[1]["data"]
        assert call_data["grant_type"] == "client_credentials"
        assert call_data["client_id"] == "client_id"
        assert call_data["client_secret"] == "client_secret"


def test_get_access_token_caching() -> None:
    """Cached token is reused within expiry window."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "cached-token",
            "expires_in": 3600,
        }

        client = OfficialEProcurementClient(
            token_url="https://example.com/token",
            client_id="id",
            client_secret="secret",
        )
        t1 = client.get_access_token()
        t2 = client.get_access_token()

        assert t1 == t2 == "cached-token"
        mock_post.assert_called_once()


def test_get_access_token_refresh_before_expiry() -> None:
    """Token is refreshed 60 seconds before expiry."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "new-token",
            "expires_in": 100,
        }

        client = OfficialEProcurementClient(
            token_url="https://example.com/token",
            client_id="id",
            client_secret="secret",
        )
        client._refresh_before_seconds = 70  # refresh when 70s left
        client.get_access_token()

        # Simulate time passing so token is within refresh window
        client._token_expires_at = time.time() + 50
        client.get_access_token()

        assert mock_post.call_count == 2


def test_search_publications_raises_when_endpoint_pending() -> None:
    """search_publications raises EProcurementEndpointNotConfiguredError when endpoint not confirmed."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "tok",
            "expires_in": 3600,
        }

        client = OfficialEProcurementClient(
            token_url="https://example.com/token",
            client_id="id",
            client_secret="secret",
            search_base_url="https://api.example.com/v1",
        )
        with pytest.raises(EProcurementEndpointNotConfiguredError) as exc_info:
            client.search_publications(term="travaux", page=1, page_size=25)
        assert "pending" in str(exc_info.value).lower() or "endpoint" in str(exc_info.value).lower()
