"""Tests for BelGov-Trace-Id header injection in e-Procurement API calls."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.official_client import OfficialEProcurementClient


def test_make_trace_id_generates_uuid() -> None:
    """_make_trace_id() generates a valid UUID v4 string."""
    trace_id = OfficialEProcurementClient._make_trace_id()
    assert isinstance(trace_id, str)
    assert len(trace_id) == 36  # UUID format: 8-4-4-4-12
    assert trace_id.count("-") == 4
    # Verify it's a valid UUID by trying to parse it
    import uuid
    parsed = uuid.UUID(trace_id)
    assert parsed.version == 4


def test_auth_headers_includes_belgov_trace_id() -> None:
    """_auth_headers() includes BelGov-Trace-Id header."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
    )
    
    with patch.object(client, "get_access_token", return_value="test-token-123"):
        headers = client._auth_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-token-123"
        assert "Accept" in headers
        assert headers["Accept"] == "application/json"
        assert "BelGov-Trace-Id" in headers
        assert headers["BelGov-Trace-Id"]  # Non-empty
        assert len(headers["BelGov-Trace-Id"]) == 36  # UUID format


def test_auth_headers_merges_extra_headers() -> None:
    """_auth_headers() merges extra headers on top of defaults."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
    )
    
    with patch.object(client, "get_access_token", return_value="test-token-123"):
        extra = {"X-Custom-Header": "custom-value"}
        headers = client._auth_headers(extra_headers=extra)
        
        assert headers["X-Custom-Header"] == "custom-value"
        assert "BelGov-Trace-Id" in headers
        assert "Authorization" in headers


def test_search_publications_includes_trace_id() -> None:
    """search_publications() includes BelGov-Trace-Id in request headers."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        search_base_url="https://api.example.com/v1",
    )
    
    # Mock endpoints and token
    from connectors.eprocurement.openapi_discovery import DiscoveredEndpoints
    client._endpoints = DiscoveredEndpoints(
        search_publications={
            "path": "/search/publications",
            "method": "GET",
            "term_param": "terms",
            "page_param": "page",
            "page_size_param": "pageSize",
        },
        cpv_label={},
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"totalCount": 0, "items": []}
            mock_response.url = "https://api.example.com/v1/search/publications?terms=test"
            mock_request.return_value = mock_response
            
            client.search_publications(term="test", page=1, page_size=5)
            
            # Verify request was made with BelGov-Trace-Id header
            assert mock_request.called
            call_kwargs = mock_request.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert "BelGov-Trace-Id" in headers
            assert headers["BelGov-Trace-Id"]  # Non-empty
            assert len(headers["BelGov-Trace-Id"]) == 36  # UUID format
            # Verify Accept-Language header is included
            assert "Accept-Language" in headers
            assert headers["Accept-Language"] == "fr"  # Default language


def test_get_cpv_label_includes_trace_id() -> None:
    """get_cpv_label() includes BelGov-Trace-Id in request headers."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    # Mock endpoints
    from connectors.eprocurement.openapi_discovery import DiscoveredEndpoints
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{code}",
            "method": "GET",
            "code_param": "code",
            "lang_param": "language",
            "path_params": ["code"],
        },
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": "45000000",
                "descriptions": [{"language": "FR", "text": "Test label"}],
            }
            mock_request.return_value = mock_response
            
            client.get_cpv_label("45000000", lang="fr")
            
            # Verify request was made with BelGov-Trace-Id header
            assert mock_request.called
            call_kwargs = mock_request.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert "BelGov-Trace-Id" in headers
            assert headers["BelGov-Trace-Id"]  # Non-empty
            assert len(headers["BelGov-Trace-Id"]) == 36  # UUID format
            # Verify Accept-Language header is included
            assert "Accept-Language" in headers
            assert headers["Accept-Language"] == "fr"  # Default language


def test_request_method_includes_trace_id() -> None:
    """request() method includes BelGov-Trace-Id in request headers."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
    )
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_request.return_value = mock_response
            
            client.request("GET", "https://api.example.com/test")
            
            # Verify request was made with BelGov-Trace-Id header
            assert mock_request.called
            call_kwargs = mock_request.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert "BelGov-Trace-Id" in headers
            assert headers["BelGov-Trace-Id"]  # Non-empty
            assert len(headers["BelGov-Trace-Id"]) == 36  # UUID format
            # Verify Accept-Language header is included
            assert "Accept-Language" in headers
            assert headers["Accept-Language"] == "fr"  # Default language


def test_auth_headers_includes_accept_language() -> None:
    """_auth_headers() includes Accept-Language header with default and custom values."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
    )
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        # Test default (fr)
        headers = client._auth_headers()
        assert "Accept-Language" in headers
        assert headers["Accept-Language"] == "fr"
        
        # Test custom language
        headers_nl = client._auth_headers(accept_language="nl")
        assert headers_nl["Accept-Language"] == "nl"
        
        # Test that other headers are still present
        assert "Authorization" in headers
        assert "Accept" in headers
        assert "BelGov-Trace-Id" in headers
