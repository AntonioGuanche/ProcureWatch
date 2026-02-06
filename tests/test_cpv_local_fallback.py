"""Unit tests for CPV local fallback and normalization."""
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


def test_cpv_normalization_removes_check_digit() -> None:
    """CPV code tries multiple candidate IDs including normalized versions."""
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
            # First candidate (raw input) returns 204, second (8-digit) returns 200
            mock_resp_204 = Mock()
            mock_resp_204.status_code = 204
            mock_resp_204.text = ""
            mock_resp_204.raise_for_status = Mock()
            
            mock_resp_200 = Mock()
            mock_resp_200.status_code = 200
            mock_resp_200.json.return_value = {"code": "45000000", "label": "Test"}
            mock_resp_200.raise_for_status = Mock()
            
            mock_request.side_effect = [mock_resp_204, mock_resp_200]
            
            # Test: "45000000-7" should try raw input first, then normalized
            client.get_cpv_label("45000000-7", lang="fr")
            
            # Verify multiple URLs were tried
            assert mock_request.call_count >= 2
            call_args_list = mock_request.call_args_list
            urls_tried = [call[0][1] if len(call[0]) > 1 else call[1].get("url", "") for call in call_args_list]
            # Should try raw input first
            assert any("/cpvs/45000000-7" in url or url.endswith("/cpvs/45000000-7") for url in urls_tried)
            # Should also try normalized 8-digit
            assert any("/cpvs/45000000" in url or url.endswith("/cpvs/45000000") for url in urls_tried)


def test_cpv_local_fallback_on_204() -> None:
    """Local CPV fallback returns label when API returns 204."""
    # Create temporary CPV file
    cpv_dir = Path("data") / "cpv"
    cpv_dir.mkdir(parents=True, exist_ok=True)
    cpv_file = cpv_dir / "cpv_labels_fr.json"
    
    cpv_map = {
        "45000000": "Travaux de construction (local)",
        "50000000": "Services de réparation (local)",
    }
    
    try:
        with open(cpv_file, "w", encoding="utf-8") as f:
            json.dump(cpv_map, f, indent=2)
        
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
                # Mock 204 No Content response
                mock_response = Mock()
                mock_response.status_code = 204
                mock_response.text = ""
                mock_response.raise_for_status = Mock()  # Don't raise on 204
                mock_request.return_value = mock_response
                
                label, response_json, status_code, raw_preview, _, _, _ = client.get_cpv_label_with_response("45000000", lang="fr")
                
                # Should return label from local fallback
                assert label == "Travaux de construction (local)"
                assert status_code == 204
                assert response_json is None
    finally:
        # Cleanup
        if cpv_file.exists():
            cpv_file.unlink()


def test_cpv_local_fallback_not_found() -> None:
    """Local CPV fallback returns None when code not in local file."""
    cpv_dir = Path("data") / "cpv"
    cpv_dir.mkdir(parents=True, exist_ok=True)
    cpv_file = cpv_dir / "cpv_labels_fr.json"
    
    cpv_map = {
        "45000000": "Travaux de construction",
    }
    
    try:
        with open(cpv_file, "w", encoding="utf-8") as f:
            json.dump(cpv_map, f, indent=2)
        
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
                mock_response = Mock()
                mock_response.status_code = 204
                mock_response.text = ""
                mock_response.raise_for_status = Mock()
                mock_request.return_value = mock_response
                
                # Code not in local file
                label, response_json, status_code, raw_preview, label_source, tried_ids, _ = client.get_cpv_label_with_response("99999999", lang="fr")
                
                # Should return None (not found locally)
                assert label is None
                assert status_code == 204
                assert label_source == "none"
                assert len(tried_ids) >= 1
    finally:
        if cpv_file.exists():
            cpv_file.unlink()


def test_extract_publication_identifier() -> None:
    """Test extract_publication_identifier with various item structures."""
    from scripts.smoke_eproc_api_calls import extract_publication_identifier
    
    # Test with direct shortLink
    item1 = {
        "shortLink": "abc123",
        "id": "pub-456",
        "title": "Test",
    }
    result1 = extract_publication_identifier(item1)
    assert result1["short_link"] == "abc123"
    assert result1["id"] == "pub-456"
    assert "shortLink" in result1["raw_keys"]
    
    # Test with nested shortLink (link.shortLink)
    item2 = {
        "id": "pub-789",
        "link": {
            "shortLink": "xyz789",
            "href": "https://example.com",
        },
        "title": "Test 2",
    }
    result2 = extract_publication_identifier(item2)
    assert result2["short_link"] == "xyz789"
    assert result2["id"] == "pub-789"
    
    # Test with nested shortLink (links.shortLink)
    item3 = {
        "links": {
            "shortLink": "nested123",
        },
        "publicationId": "pub-999",
    }
    result3 = extract_publication_identifier(item3)
    assert result3["short_link"] == "nested123"
    assert result3["id"] == "pub-999"
    
    # Test with no identifier
    item4 = {
        "title": "Test 4",
        "description": "No identifier",
    }
    result4 = extract_publication_identifier(item4)
    assert result4["short_link"] is None
    assert result4["id"] is None
    assert len(result4["raw_keys"]) == 2
    
    # Test with various ID field names
    item5 = {
        "uuid": "uuid-123",
        "reference": "ref-456",
    }
    result5 = extract_publication_identifier(item5)
    assert result5["id"] == "uuid-123"  # uuid comes before reference in search order
    assert result5["short_link"] is None
