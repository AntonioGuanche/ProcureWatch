"""Unit tests for CPV URL construction and error handling."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.bosa.official_client import OfficialEProcurementClient
from app.connectors.bosa.openapi_discovery import DiscoveredEndpoints


def test_cpv_path_substitution_with_id_param() -> None:
    """CPV path substitution works when path param is 'id'."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    # Mock endpoints with path /cpvs/{id} and path_params=["id"]
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{id}",
            "method": "GET",
            "code_param": "code",
            "lang_param": "language",
            "path_params": ["id"],
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
            
            # Verify URL construction
            assert mock_request.called
            # requests.request is called as: request(method, url, **kwargs)
            call_args = mock_request.call_args
            url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url", "")
            params = call_args[1].get("params", {})
            
            # URL should have code substituted in path
            assert url.endswith("/cpvs/45000000")
            assert "/cpvs/{id}" not in url
            # Code should NOT be in query params since it's in the path
            assert "code" not in params or params.get("code") != "45000000"


def test_cpv_path_substitution_with_single_path_param() -> None:
    """CPV path substitution works when there's exactly one path param (even if not 'code')."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    # Mock endpoints with single path param "cpvCode"
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{cpvCode}",
            "method": "GET",
            "code_param": "code",
            "lang_param": "language",
            "path_params": ["cpvCode"],
        },
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"code": "45000000", "label": "Test"}
            mock_request.return_value = mock_response
            
            client.get_cpv_label("45000000", lang="fr")
            
            # Verify URL construction
            assert mock_request.called
            # requests.request is called as: request(method, url, **kwargs)
            call_args = mock_request.call_args
            url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url", "")
            params = call_args[1].get("params", {})
            
            # URL should have code substituted
            assert url.endswith("/cpvs/45000000")
            assert "/cpvs/{cpvCode}" not in url
            # Code should NOT be in query params
            assert "code" not in params or params.get("code") != "45000000"


def test_cpv_path_substitution_code_param_matches_path_param() -> None:
    """CPV path substitution prioritizes code_param if it matches a path param."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    # Mock endpoints where code_param="cpv" matches a path param
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{cpv}/details",
            "method": "GET",
            "code_param": "cpv",  # Matches path param
            "lang_param": "language",
            "path_params": ["cpv", "other"],
        },
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"code": "45000000", "label": "Test"}
            mock_request.return_value = mock_response
            
            client.get_cpv_label("45000000", lang="fr")
            
            # Verify URL construction
            assert mock_request.called
            # requests.request is called as: request(method, url, **kwargs)
            call_args = mock_request.call_args
            url = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("url", "")
            
            # URL should have code substituted for {cpv}
            assert "/cpvs/45000000/details" in url
            assert "/cpvs/{cpv}/details" not in url


def test_cpv_label_with_response_returns_error_diagnostics() -> None:
    """get_cpv_label_with_response returns diagnostics even on HTTP errors."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{id}",
            "method": "GET",
            "code_param": "code",
            "lang_param": "language",
            "path_params": ["id"],
        },
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            # Mock HTTP 404 error with JSON error response
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "CPV code not found", "code": "NOT_FOUND"}
            mock_response.text = '{"error": "CPV code not found", "code": "NOT_FOUND"}'
            mock_response.raise_for_status.side_effect = Exception("404")
            
            # Make requests.request raise HTTPError
            import requests
            http_error = requests.HTTPError("404 Client Error")
            http_error.response = mock_response
            mock_request.side_effect = http_error
            
            label, response_json, status_code, raw_text_preview, label_source, tried_ids, _ = client.get_cpv_label_with_response("99999999", lang="fr")
            
            # Verify diagnostics are returned
            assert label is None
            assert response_json is not None
            assert response_json.get("error") == "CPV code not found"
            assert status_code == 404
            assert raw_text_preview is None  # JSON was parsed, so no text preview
            assert label_source == "none"
            assert len(tried_ids) >= 1


def test_cpv_label_with_response_handles_non_json_error() -> None:
    """get_cpv_label_with_response handles non-JSON error responses."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    client._endpoints = DiscoveredEndpoints(
        search_publications={},
        cpv_label={
            "path": "/cpvs/{id}",
            "method": "GET",
            "code_param": "code",
            "lang_param": "language",
            "path_params": ["id"],
        },
        publication_detail=None,
        updated_at="2024-01-01T00:00:00Z",
    )
    client._endpoint_confirmed = True
    
    with patch.object(client, "get_access_token", return_value="test-token"):
        with patch("requests.request") as mock_request:
            # Mock HTTP 500 error with plain text response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error: Database connection failed"
            mock_response.json.side_effect = ValueError("Not JSON")
            mock_response.raise_for_status.side_effect = Exception("500")
            
            import requests
            http_error = requests.HTTPError("500 Server Error")
            http_error.response = mock_response
            mock_request.side_effect = http_error
            
            label, response_json, status_code, raw_text_preview, label_source, tried_ids, _ = client.get_cpv_label_with_response("45000000", lang="fr")
            
            # Verify diagnostics are returned
            assert label is None
            assert response_json is None  # Not JSON
            assert status_code == 500
            assert raw_text_preview is not None
            assert "Internal Server Error" in raw_text_preview
            assert len(raw_text_preview) <= 500  # Should be truncated
            assert label_source == "none"
            assert len(tried_ids) >= 1
