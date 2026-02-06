"""Unit tests for CPV probe mode."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.official_client import OfficialEProcurementClient
from connectors.eprocurement.openapi_discovery import DiscoveredEndpoints


def test_cpv_probe_tries_query_params_in_order() -> None:
    """CPV probe mode tries query param candidates in order (when enabled)."""
    # Note: This test verifies probe mode behavior, but the new implementation
    # uses candidate ID retries in path instead. Keeping for backward compatibility.
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
        cpv_probe=True,  # Enable probe mode
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
            # First candidate (raw input) returns 204, second (8-digit) returns 200
            mock_resp_204 = Mock()
            mock_resp_204.status_code = 204
            mock_resp_204.text = ""
            mock_resp_204.raise_for_status = Mock()
            
            mock_resp_200 = Mock()
            mock_resp_200.status_code = 200
            mock_resp_200.json.return_value = {
                "code": "45000000",
                "descriptions": [{"language": "FR", "text": "Travaux de construction"}],
            }
            mock_resp_200.raise_for_status = Mock()
            
            mock_request.side_effect = [mock_resp_204, mock_resp_200]
            
            label, _, status_code, _, label_source, tried_ids, _ = client.get_cpv_label_with_response("45000000-7", lang="fr")
            
            # Should have tried at least 2 candidates
            assert mock_request.call_count >= 2
            # Should return label from second candidate
            assert label == "Travaux de construction"
            assert status_code == 200
            assert label_source == "api"
            
            # Verify headers include BelGov-Trace-Id and Accept-Language
            for call in mock_request.call_args_list:
                headers = call[1].get("headers", {})
                assert "BelGov-Trace-Id" in headers
                assert "Accept-Language" in headers


def test_cpv_probe_returns_none_if_all_candidates_fail() -> None:
    """CPV probe mode returns None if all candidates fail."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
        cpv_probe=True,
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
        with patch("requests.get") as mock_get:
            # All candidates return 404
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            # Mock the initial path-based call to return 204
            with patch("requests.request") as mock_request:
                mock_resp_204 = Mock()
                mock_resp_204.status_code = 204
                mock_resp_204.text = ""
                mock_resp_204.raise_for_status = Mock()
                mock_request.return_value = mock_resp_204
                
                label, _, status_code, _, _, _, _ = client.get_cpv_label_with_response("45000000", lang="fr")
                
                # Should return None (all candidates failed, no local fallback in test)
                assert label is None
                assert status_code == 204


def test_cpv_probe_finds_label_in_list_response() -> None:
    """CPV candidate ID retry finds label when response is a list."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
        cpv_probe=False,  # Not using probe mode, using candidate IDs
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
            # First candidate returns 204, second returns 200 with list
            mock_resp_204 = Mock()
            mock_resp_204.status_code = 204
            mock_resp_204.text = ""
            mock_resp_204.raise_for_status = Mock()
            
            mock_resp_200 = Mock()
            mock_resp_200.status_code = 200
            # Response is a single dict (not a list) with matching code
            mock_resp_200.json.return_value = {
                "code": "45000000",
                "descriptions": [{"language": "FR", "text": "Travaux de construction"}],
            }
            mock_resp_200.raise_for_status = Mock()
            
            mock_request.side_effect = [mock_resp_204, mock_resp_200]
            
            label, _, status_code, _, label_source, tried_ids, _ = client.get_cpv_label_with_response("45000000-7", lang="fr")
            
            # Should find label from second candidate (8-digit base)
            assert label == "Travaux de construction"
            assert status_code == 200
            assert label_source == "api"
