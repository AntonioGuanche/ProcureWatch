"""Unit tests for CPV candidate ID generation and retry logic."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.bosa.official_client import OfficialEProcurementClient
from app.connectors.bosa.openapi_discovery import DiscoveredEndpoints


def test_generate_cpv_candidate_ids_with_check_digit() -> None:
    """CPV candidate ID generation includes raw input, base, and full digits."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    candidates = client._generate_cpv_candidate_ids("45000000-7")
    
    # Should include: raw input, 8-digit base, full digits
    assert "45000000-7" in candidates  # Raw input
    assert "45000000" in candidates  # 8-digit base
    assert "450000007" in candidates  # Full digits (no dash)
    
    # Order should be: raw input first
    assert candidates[0] == "45000000-7"


def test_generate_cpv_candidate_ids_without_check_digit() -> None:
    """CPV candidate ID generation works without check digit."""
    client = OfficialEProcurementClient(
        token_url="https://example.com/token",
        client_id="test_id",
        client_secret="test_secret",
        loc_base_url="https://api.example.com/v1",
    )
    
    candidates = client._generate_cpv_candidate_ids("45000000")
    
    # Should include: raw input and full digits (same in this case)
    assert "45000000" in candidates
    assert len(candidates) >= 1


def test_cpv_retry_tries_candidates_in_order() -> None:
    """CPV lookup tries candidate IDs in order until success."""
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
            # First candidate returns 204, second returns 200 with label
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
            
            label, response_json, status_code, _, label_source, tried_ids, _ = client.get_cpv_label_with_response("45000000-7", lang="fr")
            
            # Should have tried at least 2 candidates
            assert mock_request.call_count >= 2
            # Should return label from second candidate
            assert label == "Travaux de construction"
            assert status_code == 200
            assert label_source == "api"
            assert len(tried_ids) >= 2
            
            # Verify URLs tried both candidate IDs
            urls_called = [call[0][1] for call in mock_request.call_args_list]
            assert any("/cpvs/45000000-7" in url or url.endswith("/cpvs/45000000-7") for url in urls_called)
            assert any("/cpvs/45000000" in url or url.endswith("/cpvs/45000000") for url in urls_called)


def test_cpv_retry_returns_none_if_all_candidates_fail() -> None:
    """CPV lookup returns None with diagnostics if all candidates return 204/404."""
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
            # All candidates return 204
            mock_resp_204 = Mock()
            mock_resp_204.status_code = 204
            mock_resp_204.text = ""
            mock_resp_204.raise_for_status = Mock()
            mock_request.return_value = mock_resp_204
            
            label, response_json, status_code, _, label_source, tried_ids, _ = client.get_cpv_label_with_response("45000000-7", lang="fr")
            
            # Should return None with diagnostics
            assert label is None
            assert status_code == 204
            assert label_source == "none"
            assert len(tried_ids) >= 1
            # Should have tried all candidates
            assert mock_request.call_count >= len(tried_ids)


def test_extract_publication_identifier_workspace_and_notice_ids() -> None:
    """extract_publication_identifier extracts publicationWorkspaceId and noticeIds."""
    from scripts.smoke_eproc_api_calls import extract_publication_identifier
    
    # Test with publicationWorkspaceId
    item1 = {
        "publicationWorkspaceId": "workspace-123",
        "noticeIds": ["notice-1", "notice-2"],
        "referenceNumber": "REF-456",
    }
    result1 = extract_publication_identifier(item1)
    assert result1["publication_workspace_id"] == "workspace-123"
    assert result1["notice_ids"] == ["notice-1", "notice-2"]
    
    # Test with single noticeIds string
    item2 = {
        "noticeIds": "notice-single",
        "referenceNumber": "REF-789",
    }
    result2 = extract_publication_identifier(item2)
    assert result2["notice_ids"] == ["notice-single"]
    assert result2["publication_workspace_id"] is None
    
    # Test with no Dos API identifiers
    item3 = {
        "referenceNumber": "REF-999",
        "title": "Test",
    }
    result3 = extract_publication_identifier(item3)
    assert result3["publication_workspace_id"] is None
    assert result3["notice_ids"] is None
    assert len(result3["raw_keys"]) == 2
