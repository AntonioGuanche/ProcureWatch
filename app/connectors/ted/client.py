"""Router for TED connector (TED_MODE: official | off)."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None


def _get_client():
    """Return official TED client when mode is official; None when off."""
    global _client
    if _client is not None:
        return _client

    from app.core.config import settings

    mode = (getattr(settings, "ted_mode", None) or "official").strip().lower()
    if mode == "off":
        logger.info("TED connector: off")
        return None

    from app.connectors.ted.official_client import OfficialTEDClient

    _client = OfficialTEDClient(
        search_base_url=settings.ted_search_base_url,
        timeout_seconds=settings.ted_timeout_seconds,
    )
    logger.info("TED connector: official")
    return _client


def search_ted_notices(
    term: str,
    page: int = 1,
    page_size: int = 25,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Search TED notices. When TED_MODE is "official", calls the TED Search API.
    When TED_MODE is "off", returns empty result with metadata.
    When debug=True, prints URL, request body, response status/headers/body (on non-2xx).
    """
    client = _get_client()
    if client is None:
        from datetime import datetime, timezone

        return {
            "metadata": {
                "term": term,
                "page": page,
                "pageSize": page_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": None,
                "status": None,
                "totalCount": None,
            },
            "json": {"notices": [], "totalCount": 0},
        }
    return client.search_notices(term=term, page=page, page_size=page_size, debug=debug)


def reset_client() -> None:
    """Reset cached client (for tests)."""
    global _client
    _client = None
