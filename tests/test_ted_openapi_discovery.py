"""Tests for TED OpenAPI discovery: mock requests.get, fake spec, cache (offline)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.ted.openapi_discovery import (
    TEDDiscoveryError,
    discover_search_notices_endpoint,
    fetch_spec,
    load_or_discover_endpoints,
)


# Minimal OpenAPI 3 spec with 3 paths: one clear "search notices" winner, others not
FAKE_SPEC = {
    "openapi": "3.0.0",
    "paths": {
        "/v3/notices/search": {
            "post": {
                "operationId": "search",
                "summary": "Search for notices",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "page": {"type": "integer"},
                                    "limit": {"type": "integer"},
                                },
                            }
                        }
                    }
                },
            }
        },
        "/v3/notices": {
            "get": {
                "operationId": "listNotices",
                "summary": "List notices",
            }
        },
        "/other/notices/search": {
            "get": {
                "operationId": "searchNoticesGet",
                "summary": "Search notices",
                "parameters": [
                    {"name": "query", "in": "query"},
                    {"name": "page", "in": "query"},
                    {"name": "limit", "in": "query"},
                ],
            }
        },
    },
}


def test_fetch_spec_404_then_200_returns_spec() -> None:
    """Mock requests.get: 404 for first candidates, then 200 with valid spec on a later candidate."""
    call_count = [0]

    def fake_get(url, timeout=None):
        call_count[0] += 1
        resp = MagicMock()
        if call_count[0] <= 2:
            resp.status_code = 404
            resp.headers = {"Content-Type": "text/plain"}
            return resp
        resp.status_code = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json.return_value = FAKE_SPEC
        return resp

    with patch("app.connectors.ted.openapi_discovery.requests.get", side_effect=fake_get):
        spec, tried = fetch_spec("https://api.ted.europa.eu", timeout=10)

    assert spec.get("paths") is not None
    assert "/v3/notices/search" in spec["paths"]
    assert len(tried) >= 2
    assert any("api.ted.europa.eu" in u for u in tried)


def test_discover_search_notices_picks_correct_path() -> None:
    """Discovery selects the best candidate: path with notices+search and term/page/limit params."""
    candidates = discover_search_notices_endpoint(FAKE_SPEC)
    assert len(candidates) >= 1
    best = candidates[0]
    assert "notices" in best.path.lower()
    assert "search" in best.path.lower()
    assert best.term_param in ("query", None)
    assert best.method in ("POST", "GET")
    # Should prefer the POST /v3/notices/search with requestBody (query, page, limit)
    path_lower = best.path.lower()
    assert "v3/notices/search" in path_lower or "notices/search" in path_lower


def test_load_or_discover_endpoints_writes_and_loads_cache(tmp_path: Path) -> None:
    """Discovery writes cache; next load reads from cache (no second fetch)."""
    def fake_fetch_spec(host, timeout=30):
        return FAKE_SPEC, [host + "/v3/api-docs"]

    cache_file = tmp_path / "ted_endpoints.json"
    with patch("app.connectors.ted.openapi_discovery.fetch_spec", side_effect=fake_fetch_spec):
        with patch("app.connectors.ted.openapi_discovery._cache_path", return_value=cache_file):
            desc = load_or_discover_endpoints(force=True, host="https://api.ted.europa.eu", timeout=10)

    assert desc.get("base_url") == "https://api.ted.europa.eu"
    assert desc.get("path")
    assert desc.get("method")
    assert desc.get("term_param")
    assert cache_file.exists()
    with open(cache_file, encoding="utf-8") as f:
        cached = json.load(f)
    assert cached.get("path") == desc.get("path")

    # Load again without force: should read from cache (fetch_spec not called again)
    with patch("app.connectors.ted.openapi_discovery.fetch_spec") as mock_fetch:
        with patch("app.connectors.ted.openapi_discovery._cache_path", return_value=cache_file):
            desc2 = load_or_discover_endpoints(force=False, host="https://api.ted.europa.eu", timeout=10)
        mock_fetch.assert_not_called()
    assert desc2.get("path") == desc.get("path")


def test_fetch_spec_raises_with_tried_urls_and_last_status_when_all_fail() -> None:
    """When all candidates fail, TEDDiscoveryError includes tried URLs and last status/body snippet."""
    with patch("app.connectors.ted.openapi_discovery.requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        mock_get.return_value.headers = {}
        mock_get.return_value.text = "Not Found"
        with pytest.raises(TEDDiscoveryError) as exc_info:
            fetch_spec("https://ted.europa.eu", timeout=5)
    msg = str(exc_info.value)
    assert "Could not find" in msg or "Tried" in msg
    assert "ted.europa.eu" in msg
    assert "Last response status" in msg or "404" in msg
