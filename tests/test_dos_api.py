"""Unit tests for Dos API methods."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.official_client import OfficialEProcurementClient
from connectors.eprocurement.openapi_discovery import DiscoveredEndpoints


def test_get_publication_workspace_url_construction() -> None:
    """get_publication_workspace constructs correct URL."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        dos_base_url="https://api.example.com/v1",
    )
    
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "workspace-123", "name": "Test"}
            mock_get.return_value = mock_response
            
            client.get_publication_workspace("workspace-123")
            
            # Verify URL construction
            assert mock_get.called
            call_args = mock_get.call_args
            url = call_args[0][0]
            assert url == "https://api.example.com/v1/publication-workspaces/workspace-123"
            
            # Verify headers include BelGov-Trace-Id and Accept-Language
            headers = call_args[1].get("headers", {})
            assert "BelGov-Trace-Id" in headers
            assert "Accept-Language" in headers
            assert headers["Accept-Language"] == "fr"


def test_get_notice_url_construction() -> None:
    """get_notice constructs correct URL."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        dos_base_url="https://api.example.com/v1",
    )
    
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "notice-456", "title": "Test Notice"}
            mock_get.return_value = mock_response
            
            client.get_notice("notice-456")
            
            # Verify URL construction
            assert mock_get.called
            call_args = mock_get.call_args
            url = call_args[0][0]
            assert url == "https://api.example.com/v1/notices/notice-456"
            
            # Verify headers include BelGov-Trace-Id and Accept-Language
            headers = call_args[1].get("headers", {})
            assert "BelGov-Trace-Id" in headers
            assert "Accept-Language" in headers


def test_get_publication_workspace_returns_none_on_404() -> None:
    """get_publication_workspace returns None on 404."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        dos_base_url="https://api.example.com/v1",
    )
    
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            result = client.get_publication_workspace("nonexistent")
            
            assert result is None


def test_get_notice_returns_none_on_403() -> None:
    """get_notice returns None on 403."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        dos_base_url="https://api.example.com/v1",
    )
    
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 403
            mock_get.return_value = mock_response
            
            result = client.get_notice("forbidden")
            
            assert result is None


def test_get_publication_workspace_raises_if_dos_base_url_missing() -> None:
    """get_publication_workspace raises error if dos_base_url is not set."""
    from connectors.eprocurement.exceptions import EProcurementEndpointNotConfiguredError
    
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        dos_base_url=None,  # Not set
    )
    
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        try:
            client.get_publication_workspace("workspace-123")
            assert False, "Should have raised EProcurementEndpointNotConfiguredError"
        except EProcurementEndpointNotConfiguredError as e:
            assert "EPROC_DOS_BASE_URL" in str(e)
