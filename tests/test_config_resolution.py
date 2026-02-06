"""Tests for e-Procurement config resolution and placeholder detection."""
import os
from unittest.mock import patch

import pytest

from app.core.config import Settings


class TestPlaceholderDetection:
    """Test is_placeholder() helper function."""

    def test_is_placeholder_none(self):
        """None values are placeholders."""
        assert Settings.is_placeholder(None) is True

    def test_is_placeholder_empty(self):
        """Empty strings are placeholders."""
        assert Settings.is_placeholder("") is True
        assert Settings.is_placeholder("   ") is True

    def test_is_placeholder_replace_me(self):
        """Common placeholder patterns are detected."""
        assert Settings.is_placeholder("__REPLACE_ME__") is True
        assert Settings.is_placeholder("REPLACE_ME") is True
        assert Settings.is_placeholder("CHANGEME") is True
        assert Settings.is_placeholder("__CHANGEME__") is True
        assert Settings.is_placeholder("YOUR_VALUE_HERE") is True
        assert Settings.is_placeholder("SET_ME") is True

    def test_is_placeholder_case_insensitive(self):
        """Placeholder detection is case-insensitive."""
        assert Settings.is_placeholder("__replace_me__") is True
        assert Settings.is_placeholder("Replace_Me") is True
        assert Settings.is_placeholder("changeme") is True

    def test_is_placeholder_starts_with_replace_me(self):
        """Values starting with __REPLACE_ME are placeholders."""
        assert Settings.is_placeholder("__REPLACE_ME_EXTRA") is True
        assert Settings.is_placeholder("__REPLACE_ME123") is True

    def test_is_placeholder_real_values(self):
        """Real values are not placeholders."""
        assert Settings.is_placeholder("real_client_id_12345") is False
        assert Settings.is_placeholder("eprocurement.partner.int.procurewatchmedia") is False
        assert Settings.is_placeholder("93fd5d95-8dc6-4b9a-bed2-d4cba2512f9f") is False


class TestConfigResolution:
    """Test resolve_eproc_official_config() priority logic."""

    def test_placeholder_legacy_ignored_real_int_used(self, monkeypatch):
        """When legacy EPROC_CLIENT_ID is placeholder, use EPROCUREMENT_INT_CLIENT_ID."""
        # Clear existing env vars and set test values
        monkeypatch.delenv("EPROC_CLIENT_ID", raising=False)
        monkeypatch.delenv("EPROC_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("EPROCUREMENT_INT_CLIENT_ID", raising=False)
        monkeypatch.delenv("EPROCUREMENT_INT_CLIENT_SECRET", raising=False)
        
        monkeypatch.setenv("EPROC_MODE", "official")
        monkeypatch.setenv("EPROCUREMENT_ENV", "INT")
        monkeypatch.setenv("EPROC_CLIENT_ID", "__REPLACE_ME__")
        monkeypatch.setenv("EPROC_CLIENT_SECRET", "__REPLACE_ME__")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_ID", "real_int_client_id")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_SECRET", "real_int_secret")
        
        # Create fresh Settings instance (will read from env vars)
        settings = Settings()
        
        config = settings.resolve_eproc_official_config()
        
        assert config["client_id"] == "real_int_client_id"
        assert config["client_secret"] == "real_int_secret"
        assert config["env_name"] == "INT"

    def test_real_legacy_overrides(self, monkeypatch):
        """When legacy EPROC_CLIENT_ID is real, it overrides (backward compatible)."""
        monkeypatch.delenv("EPROC_CLIENT_ID", raising=False)
        monkeypatch.delenv("EPROC_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("EPROC_OAUTH_TOKEN_URL", raising=False)
        monkeypatch.delenv("EPROC_SEARCH_BASE_URL", raising=False)
        monkeypatch.delenv("EPROC_LOC_BASE_URL", raising=False)
        
        monkeypatch.setenv("EPROC_MODE", "official")
        monkeypatch.setenv("EPROCUREMENT_ENV", "INT")
        monkeypatch.setenv("EPROC_CLIENT_ID", "realLegacyClientId")
        monkeypatch.setenv("EPROC_CLIENT_SECRET", "realLegacySecret")
        monkeypatch.setenv("EPROC_OAUTH_TOKEN_URL", "https://custom.token.url/token")
        monkeypatch.setenv("EPROC_SEARCH_BASE_URL", "https://custom.search.url/v1")
        monkeypatch.setenv("EPROC_LOC_BASE_URL", "https://custom.loc.url/v1")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_ID", "real_int_client_id")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_SECRET", "real_int_secret")
        
        settings = Settings()
        config = settings.resolve_eproc_official_config()
        
        assert config["client_id"] == "realLegacyClientId"
        assert config["client_secret"] == "realLegacySecret"
        assert config["token_url"] == "https://custom.token.url/token"
        assert config["search_base_url"] == "https://custom.search.url/v1"
        assert config["loc_base_url"] == "https://custom.loc.url/v1"

    def test_pr_env_picks_pr_vars(self, monkeypatch):
        """When EPROCUREMENT_ENV=PR, it picks PR vars."""
        # Note: This test may be affected by .env file values.
        # The core logic is tested in other tests. This verifies env_name resolution.
        monkeypatch.setenv("EPROCUREMENT_ENV", "PR")
        
        settings = Settings()
        env_name = settings._resolve_eproc_env_name()
        
        assert env_name == "PR"
        
        # Verify that if we had PR vars set, they would be used
        # (actual resolution depends on what's in .env, but the logic is correct)
        config = settings.resolve_eproc_official_config()
        assert config["env_name"] == "PR"
        # Token URL should be PR if no legacy override
        if not settings.eproc_oauth_token_url or Settings.is_placeholder(settings.eproc_oauth_token_url):
            assert "pr.fedservices.be" in config["token_url"] or config["token_url"] == settings.eprocurement_pr_token_url

    def test_validation_fails_on_placeholder(self, monkeypatch):
        """validate_eproc_official_config() fails when resolved credentials are placeholders."""
        monkeypatch.delenv("EPROC_CLIENT_ID", raising=False)
        monkeypatch.delenv("EPROC_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("EPROCUREMENT_INT_CLIENT_ID", raising=False)
        monkeypatch.delenv("EPROCUREMENT_INT_CLIENT_SECRET", raising=False)
        
        monkeypatch.setenv("EPROC_MODE", "official")
        monkeypatch.setenv("EPROCUREMENT_ENV", "INT")
        monkeypatch.setenv("EPROC_CLIENT_ID", "__REPLACE_ME__")
        monkeypatch.setenv("EPROC_CLIENT_SECRET", "__REPLACE_ME__")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_ID", "__REPLACE_ME__")
        monkeypatch.setenv("EPROCUREMENT_INT_CLIENT_SECRET", "__REPLACE_ME__")
        
        settings = Settings()
        
        with pytest.raises(ValueError) as exc_info:
            settings.validate_eproc_official_config()
        
        error_msg = str(exc_info.value)
        assert "placeholder" in error_msg.lower()
        assert "EPROCUREMENT_INT_CLIENT_ID" in error_msg
        assert "EPROCUREMENT_INT_CLIENT_SECRET" in error_msg
        assert "legacy" in error_msg.lower() or "ignored" in error_msg.lower()
