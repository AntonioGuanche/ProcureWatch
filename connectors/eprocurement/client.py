"""Provider router for Belgian e-Procurement (official API vs Playwright fallback)."""
import logging
from typing import Any, Optional

from connectors.eprocurement.official_client import (
    EProcurementCredentialsError,
    EProcurementEndpointNotConfiguredError,
    OfficialEProcurementClient,
)
from connectors.eprocurement.playwright_client import (
    PlaywrightCollectorError,
    PlaywrightEProcurementClient,
)

logger = logging.getLogger(__name__)

# Lazy-initialized client (set by _get_client())
_client: Optional[OfficialEProcurementClient | PlaywrightEProcurementClient] = None
_provider_name: Optional[str] = None


def _get_client():  # noqa: ANN202
    """Resolve provider from config and return the appropriate client instance."""
    global _client, _provider_name

    if _client is not None:
        return _client, _provider_name

    from app.core.config import settings

    mode = (getattr(settings, "eproc_mode", None) or "auto").strip().lower()
    client_id = getattr(settings, "eproc_client_id", None) or ""
    client_secret = getattr(settings, "eproc_client_secret", None) or ""

    if mode == "official":
        if not client_id or not client_secret:
            raise EProcurementCredentialsError(
                "EPROC_MODE=official requires EPROC_CLIENT_ID and EPROC_CLIENT_SECRET."
            )
        _client = OfficialEProcurementClient(
            token_url=settings.eproc_oauth_token_url,
            client_id=client_id,
            client_secret=client_secret,
            search_base_url=settings.eproc_search_base_url,
            loc_base_url=settings.eproc_loc_base_url,
            timeout_seconds=settings.eproc_timeout_seconds,
        )
        _provider_name = "official"
        logger.info("e-Procurement provider: official (OAuth2)")
        return _client, _provider_name

    if mode == "playwright":
        _client = PlaywrightEProcurementClient(timeout_seconds=settings.eproc_timeout_seconds)
        _provider_name = "playwright"
        logger.info("e-Procurement provider: playwright (fallback)")
        return _client, _provider_name

    # auto: use official if credentials present, else playwright
    if client_id and client_secret:
        try:
            _client = OfficialEProcurementClient(
                token_url=settings.eproc_oauth_token_url,
                client_id=client_id,
                client_secret=client_secret,
                search_base_url=settings.eproc_search_base_url,
                loc_base_url=settings.eproc_loc_base_url,
                timeout_seconds=settings.eproc_timeout_seconds,
            )
            _provider_name = "official"
            logger.info("e-Procurement provider: official (auto, credentials found)")
            return _client, _provider_name
        except Exception as e:
            logger.warning("Official client init failed in auto mode: %s; falling back to playwright", e)
            _client = PlaywrightEProcurementClient(timeout_seconds=settings.eproc_timeout_seconds)
            _provider_name = "playwright"
            logger.info("e-Procurement provider: playwright (auto fallback)")
            return _client, _provider_name

    _client = PlaywrightEProcurementClient(timeout_seconds=settings.eproc_timeout_seconds)
    _provider_name = "playwright"
    logger.info("e-Procurement provider: playwright (auto, no credentials)")
    return _client, _provider_name


def search_publications(
    term: str,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """
    Search publications using the configured provider (official or playwright).
    Returns structure: {"metadata": {...}, "json": {...}}
    """
    client, name = _get_client()

    if name == "official":
        return client.search_publications(term=term, page=page, page_size=page_size)

    # Playwright
    return client.search_publications(term=term, page=page, page_size=page_size)


def get_publication_detail(publication_id: str) -> Optional[dict[str, Any]]:
    """Get a single publication by ID (official only; playwright returns None)."""
    client, _ = _get_client()
    return client.get_publication_detail(publication_id)


def get_cpv_label(code: str, lang: str = "fr") -> Optional[str]:
    """Get CPV code label (official only; playwright returns None)."""
    client, _ = _get_client()
    return client.get_cpv_label(code=code, lang=lang)


def reset_client() -> None:
    """Reset cached client (for tests)."""
    global _client, _provider_name
    _client = None
    _provider_name = None
