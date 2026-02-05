"""Offline unit tests for Playwright collector output (no network).

Helpers and assertions for totalCount extraction and publications/items presence,
using fake generateShortLink and byShortLink responses.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def extract_total_count(data: dict | None) -> int | None:
    """Best-effort extraction of totalCount from byShortLink-style JSON."""
    if data is None or not isinstance(data, dict):
        return None
    if isinstance(data.get("totalCount"), int):
        return data["totalCount"]
    if isinstance(data.get("total"), int):
        return data["total"]
    if isinstance(data.get("itemsCount"), int):
        return data["itemsCount"]
    for key in ("publications", "items", "results"):
        arr = data.get(key)
        if isinstance(arr, list):
            return len(arr)
    return None


def has_publications_or_items(data: dict | None) -> bool:
    """True if data contains a list of publications/items/results."""
    if data is None or not isinstance(data, dict):
        return False
    for key in ("publications", "items", "results"):
        val = data.get(key)
        if isinstance(val, list) and len(val) > 0:
            return True
    return False


def build_collector_output_from_by_shortlink(
    by_shortlink_json: dict,
    *,
    term: str = "travaux",
    page: int = 1,
    page_size: int = 25,
    url: str = "https://www.publicprocurement.be/api/sea/search/publications/byShortLink/xxx",
    status: int = 200,
) -> dict:
    """Build the final collector output structure as the Node script would produce."""
    total_count = extract_total_count(by_shortlink_json)
    from datetime import datetime, timezone

    return {
        "metadata": {
            "term": term,
            "page": page,
            "pageSize": page_size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "status": status,
            "totalCount": total_count,
        },
        "json": by_shortlink_json,
    }


# --- Fake responses for tests ---

FAKE_GENERATE_SHORTLINK_RESPONSE = {"link": "-e6xv3s"}

FAKE_BY_SHORTLINK_RESPONSE_WITH_PUBLICATIONS = {
    "publications": [
        {"id": "pub-1", "title": "Notice 1"},
        {"id": "pub-2", "title": "Notice 2"},
    ],
    "totalCount": 42,
}

FAKE_BY_SHORTLINK_RESPONSE_WITH_ITEMS = {
    "items": [{"id": "1"}, {"id": "2"}],
    "total": 100,
}

FAKE_BY_SHORTLINK_RESPONSE_EMPTY = {
    "publications": [],
    "totalCount": 0,
}

FAKE_BY_SHORTLINK_RESPONSE_LINK_ONLY = {"link": "-e6xv3s"}


def test_extract_total_count_from_publications() -> None:
    """extract_total_count returns totalCount from byShortLink-style JSON."""
    assert extract_total_count(FAKE_BY_SHORTLINK_RESPONSE_WITH_PUBLICATIONS) == 42
    assert extract_total_count(FAKE_BY_SHORTLINK_RESPONSE_WITH_ITEMS) == 100
    assert extract_total_count(FAKE_BY_SHORTLINK_RESPONSE_EMPTY) == 0


def test_extract_total_count_fallback() -> None:
    """extract_total_count falls back to total/itemsCount or list length."""
    assert extract_total_count({"total": 10}) == 10
    assert extract_total_count({"itemsCount": 5}) == 5
    assert extract_total_count({"publications": [1, 2, 3]}) == 3
    assert extract_total_count(FAKE_BY_SHORTLINK_RESPONSE_LINK_ONLY) is None


def test_has_publications_or_items() -> None:
    """has_publications_or_items is True when publications/items/results list has length > 0."""
    assert has_publications_or_items(FAKE_BY_SHORTLINK_RESPONSE_WITH_PUBLICATIONS) is True
    assert has_publications_or_items(FAKE_BY_SHORTLINK_RESPONSE_WITH_ITEMS) is True
    assert has_publications_or_items(FAKE_BY_SHORTLINK_RESPONSE_EMPTY) is False
    assert has_publications_or_items(FAKE_BY_SHORTLINK_RESPONSE_LINK_ONLY) is False
    assert has_publications_or_items({"results": [{"x": 1}]}) is True


def test_build_collector_output_and_verify() -> None:
    """Fake generateShortLink + byShortLink: final output has totalCount and publications."""
    # Simulate: we got link from generateShortLink, then byShortLink returned publications
    by_shortlink_json = FAKE_BY_SHORTLINK_RESPONSE_WITH_PUBLICATIONS
    output = build_collector_output_from_by_shortlink(by_shortlink_json)

    assert "metadata" in output
    assert "json" in output
    assert output["metadata"]["url"].endswith("/byShortLink/xxx")
    assert output["metadata"]["totalCount"] == 42
    assert output["metadata"]["status"] == 200
    assert output["json"] is by_shortlink_json

    assert extract_total_count(output["json"]) == 42
    assert has_publications_or_items(output["json"]) is True


def test_fake_link_only_response_fails_verification() -> None:
    """If byShortLink returned only { link } (wrong endpoint), we have no publications."""
    output = build_collector_output_from_by_shortlink(FAKE_BY_SHORTLINK_RESPONSE_LINK_ONLY)
    assert extract_total_count(output["json"]) is None
    assert has_publications_or_items(output["json"]) is False
