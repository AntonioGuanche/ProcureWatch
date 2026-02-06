"""Unit tests for BOSA e-Procurement OAuth2 configuration."""
import os
from unittest.mock import Mock, patch

import pytest
import requests

from app.core.config import Settings


def _create_settings(**kwargs):
    """Create Settings instance bypassing .env file loading."""
    # Start with minimal required fields
    defaults = {
        "database_url": "sqlite+pysqlite:///:memory:",
    }
    defaults.update(kwargs)
    # Use model_construct to bypass .env file loading and validation
    return Settings.model_construct(**defaults)


@pytest.fixture
def mock_token_response():
    """Mock successful OAuth token response."""
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "test_token_12345",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    mock_resp.raise_for_status = Mock()
    return mock_resp


def test_bosa_token_url_int():
    """Test that INT environment uses INT token URL."""
    settings = _create_settings(
        eprocurement_env="INT",
        eprocurement_int_token_url="https://public.int.fedservices.be/api/oauth2/token",
        eprocurement_pr_token_url="https://public.pr.fedservices.be/api/oauth2/token",
    )
    assert settings.bosa_token_url == "https://public.int.fedservices.be/api/oauth2/token"


def test_bosa_token_url_pr():
    """Test that PR environment uses PR token URL."""
    settings = _create_settings(
        eprocurement_env="PR",
        eprocurement_int_token_url="https://public.int.fedservices.be/api/oauth2/token",
        eprocurement_pr_token_url="https://public.pr.fedservices.be/api/oauth2/token",
    )
    assert settings.bosa_token_url == "https://public.pr.fedservices.be/api/oauth2/token"


def test_bosa_client_id_int():
    """Test that INT environment uses INT client ID."""
    settings = _create_settings(
        eprocurement_env="INT",
        eprocurement_int_client_id="int_client_id",
        eprocurement_pr_client_id="pr_client_id",
    )
    assert settings.bosa_client_id == "int_client_id"


def test_bosa_client_id_pr():
    """Test that PR environment uses PR client ID."""
    settings = _create_settings(
        eprocurement_env="PR",
        eprocurement_int_client_id="int_client_id",
        eprocurement_pr_client_id="pr_client_id",
    )
    assert settings.bosa_client_id == "pr_client_id"


def test_bosa_client_secret_int():
    """Test that INT environment uses INT client secret."""
    settings = _create_settings(
        eprocurement_env="INT",
        eprocurement_int_client_secret="int_secret",
        eprocurement_pr_client_secret="pr_secret",
    )
    assert settings.bosa_client_secret == "int_secret"


def test_bosa_client_secret_pr():
    """Test that PR environment uses PR client secret."""
    settings = _create_settings(
        eprocurement_env="PR",
        eprocurement_int_client_secret="int_secret",
        eprocurement_pr_client_secret="pr_secret",
    )
    assert settings.bosa_client_secret == "pr_secret"


def test_bosa_oauth_request_int(mock_token_response):
    """Test OAuth token request for INT environment with correct URL and headers."""
    settings = _create_settings(
        eprocurement_env="INT",
        eprocurement_int_token_url="https://public.int.fedservices.be/api/oauth2/token",
        eprocurement_int_client_id="test_int_id",
        eprocurement_int_client_secret="test_int_secret",
    )

    with patch("requests.post", return_value=mock_token_response) as mock_post:
        response = requests.post(
            settings.bosa_token_url,
            data={
                "client_id": settings.bosa_client_id,
                "client_secret": settings.bosa_client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Verify request was made with correct URL
        assert mock_post.called
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://public.int.fedservices.be/api/oauth2/token"

        # Verify request data contains correct fields
        request_data = call_args[1]["data"]
        assert request_data["client_id"] == "test_int_id"
        assert request_data["client_secret"] == "test_int_secret"
        assert request_data["grant_type"] == "client_credentials"

        # Verify headers
        headers = call_args[1]["headers"]
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"

        # Verify response
        assert data["access_token"] == "test_token_12345"
        assert data["expires_in"] == 3600


def test_bosa_oauth_request_pr(mock_token_response):
    """Test OAuth token request for PR environment with correct URL and headers."""
    settings = _create_settings(
        eprocurement_env="PR",
        eprocurement_pr_token_url="https://public.pr.fedservices.be/api/oauth2/token",
        eprocurement_pr_client_id="test_pr_id",
        eprocurement_pr_client_secret="test_pr_secret",
    )

    with patch("requests.post", return_value=mock_token_response) as mock_post:
        response = requests.post(
            settings.bosa_token_url,
            data={
                "client_id": settings.bosa_client_id,
                "client_secret": settings.bosa_client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Verify request was made with correct URL
        assert mock_post.called
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://public.pr.fedservices.be/api/oauth2/token"

        # Verify request data contains correct fields
        request_data = call_args[1]["data"]
        assert request_data["client_id"] == "test_pr_id"
        assert request_data["client_secret"] == "test_pr_secret"
        assert request_data["grant_type"] == "client_credentials"

        # Verify headers
        headers = call_args[1]["headers"]
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"

        # Verify response
        assert data["access_token"] == "test_token_12345"
        assert data["expires_in"] == 3600


def test_bosa_oauth_case_insensitive_env():
    """Test that environment is case-insensitive (int, INT, Int all work)."""
    settings_lower = _create_settings(
        eprocurement_env="int",
        eprocurement_int_token_url="https://public.int.fedservices.be/api/oauth2/token",
        eprocurement_pr_token_url="https://public.pr.fedservices.be/api/oauth2/token",
    )
    assert settings_lower.bosa_token_url == "https://public.int.fedservices.be/api/oauth2/token"

    settings_upper = _create_settings(
        eprocurement_env="PR",
        eprocurement_int_token_url="https://public.int.fedservices.be/api/oauth2/token",
        eprocurement_pr_token_url="https://public.pr.fedservices.be/api/oauth2/token",
    )
    assert settings_upper.bosa_token_url == "https://public.pr.fedservices.be/api/oauth2/token"
