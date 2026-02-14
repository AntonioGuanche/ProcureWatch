"""Tests for TED official client: mock Session.request, verify expert query, fields, notices parsing (offline)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.ted.official_client import (
    OfficialTEDClient,
    build_expert_query,
)


def test_build_expert_query_keyword_becomes_or_expression() -> None:
    """Keyword term like 'solar' becomes OR expression across notice-title, description-glo, title-proc."""
    query = build_expert_query("solar")
    assert "notice-title" in query
    assert "description-glo" in query
    assert "title-proc" in query
    assert " OR " in query
    assert "solar" in query
    assert query.startswith("(") and query.count("(") >= 3


def test_build_expert_query_expert_query_passed_unchanged() -> None:
    """Expert query containing operators (~, OR, etc.) is passed unchanged."""
    expert = '(notice-title ~ "solar") AND (publication-date >= "2024-01-01")'
    result = build_expert_query(expert)
    assert result == expert
    
    expert2 = 'notice-title ~ "test" OR buyer-name = "Ministry"'
    result2 = build_expert_query(expert2)
    assert result2 == expert2


def test_build_expert_query_escapes_double_quotes() -> None:
    """Double quotes in term are escaped in the built query."""
    query = build_expert_query('term with "quotes"')
    assert '\\"' in query or '"quotes"' in query


def test_search_notices_uses_hardcoded_path_and_expert_query() -> None:
    """Client uses hardcoded /v3/notices/search, builds expert query, includes fields."""
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = "https://api.ted.europa.eu/v3/notices/search"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"notices": [{"noticeId": "TED-1"}], "totalCount": 1}
        mock_session.request.return_value = mock_resp

        client = OfficialTEDClient(
            search_base_url="https://api.ted.europa.eu",
            timeout_seconds=30,
        )
        result = client.search_notices(term="solar", page=2, page_size=10)

        assert result["metadata"]["term"] == "solar"
        assert result["metadata"]["page"] == 2
        assert result["metadata"]["pageSize"] == 10
        assert result["metadata"]["status"] == 200
        assert result["metadata"]["url"] == "https://api.ted.europa.eu/v3/notices/search"
        assert result["metadata"]["totalCount"] == 1
        assert "notices" in result
        assert len(result["notices"]) == 1

        call = mock_session.request.call_args
        assert call[0][0] == "POST"
        assert call[0][1] == "https://api.ted.europa.eu/v3/notices/search"
        kwargs = call[1]
        assert kwargs["timeout"] == 30
        body = kwargs["json"]
        assert "query" in body
        assert " OR " in body["query"]  # Expert query built
        assert "solar" in body["query"]
        assert "fields" in body
        assert isinstance(body["fields"], list)
        assert len(body["fields"]) > 0
        assert body["page"] == 2
        assert body["limit"] == 10
        assert body.get("scope") == "ALL"
        assert body.get("paginationMode") == "PAGE_NUMBER"


def test_search_notices_request_body_always_contains_non_empty_fields() -> None:
    """Request body always contains non-empty fields array (default or provided)."""
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = "https://api.ted.europa.eu/v3/notices/search"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"notices": [], "totalCount": 0}
        mock_session.request.return_value = mock_resp

        client = OfficialTEDClient(search_base_url="https://api.ted.europa.eu")
        # Without fields parameter
        client.search_notices(term="test", page=1, page_size=25)
        call1 = mock_session.request.call_args
        body1 = call1[1]["json"]
        assert "fields" in body1
        assert isinstance(body1["fields"], list)
        assert len(body1["fields"]) > 0

        # With custom fields
        custom_fields = ["publication-number", "notice-title"]
        client.search_notices(term="test", page=1, page_size=25, fields=custom_fields)
        call2 = mock_session.request.call_args
        body2 = call2[1]["json"]
        assert body2["fields"] == custom_fields


def test_search_notices_parses_notices_from_response() -> None:
    """Response parsing extracts notices array and totalCount correctly."""
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = "https://api.ted.europa.eu/v3/notices/search"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {
            "notices": [
                {"noticeId": "TED-001", "notice-title": "Test 1"},
                {"noticeId": "TED-002", "notice-title": "Test 2"},
            ],
            "totalCount": 2,
        }
        mock_session.request.return_value = mock_resp

        client = OfficialTEDClient(search_base_url="https://api.ted.europa.eu")
        result = client.search_notices(term="test", page=1, page_size=25)

        assert result["metadata"]["totalCount"] == 2
        assert "notices" in result
        assert len(result["notices"]) == 2
        assert result["notices"][0]["noticeId"] == "TED-001"
        assert result["json"]["notices"][0]["noticeId"] == "TED-001"


def test_search_notices_400_includes_response_body_in_exception() -> None:
    """On 4xx the raised exception message includes the response body (truncated)."""
    import requests

    error_body = '{"error": "Invalid query parameter", "code": "BAD_REQUEST"}'
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.reason = "Bad Request"
        mock_resp.url = "https://api.ted.europa.eu/v3/notices/search"
        mock_resp.text = error_body
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.request = MagicMock()
        mock_session.request.return_value = mock_resp

        client = OfficialTEDClient(search_base_url="https://api.ted.europa.eu")
        with pytest.raises(requests.HTTPError) as exc_info:
            client.search_notices(term="x", page=1, page_size=25)
        msg = str(exc_info.value)
        assert "400" in msg
        assert "Invalid query parameter" in msg or "BAD_REQUEST" in msg


def test_search_notices_html_response_raises_wrong_endpoint() -> None:
    """When response is HTML (wrong endpoint), raise ValueError with 'wrong endpoint' message."""
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = "https://ted.europa.eu/some-page"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.text = "<!DOCTYPE html><html><body>TED website</body></html>"
        mock_session.request.return_value = mock_resp

        client = OfficialTEDClient(search_base_url="https://api.ted.europa.eu")
        with pytest.raises(ValueError) as exc_info:
            client.search_notices(term="solar", page=1, page_size=25)
        msg = str(exc_info.value)
        assert "Received HTML" in msg
        assert "wrong endpoint" in msg
