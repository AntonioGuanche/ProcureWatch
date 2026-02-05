"""Tests for e-Procurement client provider selection (no network)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.client import (
    _get_client,
    get_cpv_label,
    get_publication_detail,
    reset_client,
)
from connectors.eprocurement.official_client import EProcurementCredentialsError
from connectors.eprocurement.playwright_client import PlaywrightEProcurementClient


@pytest.fixture(autouse=True)
def reset_client_cache() -> None:
    """Reset client cache before each test."""
    reset_client()
    yield
    reset_client()


def _make_settings(mode: str, client_id: str | None, client_secret: str | None) -> MagicMock:
    s = MagicMock()
    s.eproc_mode = mode
    s.eproc_client_id = client_id
    s.eproc_client_secret = client_secret
    s.eproc_oauth_token_url = "https://token.example.com"
    s.eproc_search_base_url = "https://search.example.com"
    s.eproc_loc_base_url = "https://loc.example.com"
    s.eproc_timeout_seconds = 30
    return s


def test_auto_mode_uses_playwright_when_no_credentials() -> None:
    """Auto mode selects Playwright when CLIENT_ID and CLIENT_SECRET are not set."""
    mock_settings = _make_settings("auto", None, None)
    with patch("app.core.config.settings", mock_settings):
        client, name = _get_client()
        assert name == "playwright"
        assert isinstance(client, PlaywrightEProcurementClient)


def test_playwright_mode_force_playwright() -> None:
    """EPROC_MODE=playwright forces Playwright client."""
    mock_settings = _make_settings("playwright", "id", "secret")
    with patch("app.core.config.settings", mock_settings):
        client, name = _get_client()
        assert name == "playwright"
        assert isinstance(client, PlaywrightEProcurementClient)


def test_official_mode_requires_credentials() -> None:
    """EPROC_MODE=official without credentials raises EProcurementCredentialsError."""
    mock_settings = _make_settings("official", None, None)
    with patch("app.core.config.settings", mock_settings):
        with pytest.raises(EProcurementCredentialsError) as exc_info:
            _get_client()
        assert "EPROC_MODE=official" in str(exc_info.value)


def test_official_mode_uses_official_client_when_credentials_set() -> None:
    """EPROC_MODE=official with credentials returns OfficialEProcurementClient."""
    from connectors.eprocurement.official_client import OfficialEProcurementClient

    mock_settings = _make_settings("official", "id", "secret")
    with patch("app.core.config.settings", mock_settings):
        client, name = _get_client()
        assert name == "official"
        assert isinstance(client, OfficialEProcurementClient)


def test_get_publication_detail_playwright_returns_none() -> None:
    """Playwright client returns None for get_publication_detail."""
    reset_client()
    mock_settings = _make_settings("playwright", None, None)
    with patch("app.core.config.settings", mock_settings):
        result = get_publication_detail("some-id")
        assert result is None


def test_get_cpv_label_playwright_returns_none() -> None:
    """Playwright client returns None for get_cpv_label."""
    reset_client()
    mock_settings = _make_settings("playwright", None, None)
    with patch("app.core.config.settings", mock_settings):
        result = get_cpv_label("45000000", "fr")
        assert result is None
