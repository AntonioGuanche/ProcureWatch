"""Phase 13: Auth, admin key protection, rate limiting, security headers."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client_no_key():
    """App with ADMIN_API_KEY set — admin requires key."""
    with patch.dict("os.environ", {"ADMIN_API_KEY": "test-secret-key-123"}):
        # Re-import to pick up new settings
        from importlib import reload
        import app.core.config as cfg_mod
        reload(cfg_mod)
        import app.core.auth as auth_mod
        reload(auth_mod)
        import app.api.routes.admin as admin_mod
        reload(admin_mod)
        import app.main as main_mod
        reload(main_mod)
        yield TestClient(main_mod.app)


@pytest.fixture
def client_dev_mode():
    """App with no ADMIN_API_KEY — dev mode, admin open."""
    with patch.dict("os.environ", {"ADMIN_API_KEY": ""}, clear=False):
        from importlib import reload
        import app.core.config as cfg_mod
        reload(cfg_mod)
        import app.core.auth as auth_mod
        reload(auth_mod)
        import app.api.routes.admin as admin_mod
        reload(admin_mod)
        import app.main as main_mod
        reload(main_mod)
        yield TestClient(main_mod.app)


# ── Admin key tests ──────────────────────────────────────────────────


class TestAdminKeyProtection:
    """Admin endpoints must require X-Admin-Key when configured."""

    def test_admin_no_key_returns_401(self, client_no_key):
        """No header → 401."""
        resp = client_no_key.get("/api/admin/import-runs?limit=1")
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    def test_admin_wrong_key_returns_403(self, client_no_key):
        """Wrong key → 403."""
        resp = client_no_key.get(
            "/api/admin/import-runs?limit=1",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403
        assert "Invalid" in resp.json()["detail"]

    def test_admin_correct_key_passes(self, client_no_key):
        """Correct key → succeeds (200 or other non-auth error)."""
        resp = client_no_key.get(
            "/api/admin/import-runs?limit=1",
            headers={"X-Admin-Key": "test-secret-key-123"},
        )
        # Should not be 401/403
        assert resp.status_code not in (401, 403)

    def test_admin_dev_mode_open(self, client_dev_mode):
        """No ADMIN_API_KEY configured → admin is open (dev mode)."""
        resp = client_dev_mode.get("/api/admin/import-runs?limit=1")
        assert resp.status_code not in (401, 403)


# ── Public endpoints remain open ─────────────────────────────────────


class TestPublicEndpointsOpen:
    """Search, facets, health must remain accessible without auth."""

    def test_health_open(self, client_no_key):
        resp = client_no_key.get("/health")
        assert resp.status_code == 200

    def test_search_open(self, client_no_key):
        resp = client_no_key.get("/api/notices/search?q=test&page_size=1")
        # 200 or 500 (no DB) but NOT 401/403
        assert resp.status_code not in (401, 403)

    def test_facets_open(self, client_no_key):
        resp = client_no_key.get("/api/notices/facets")
        assert resp.status_code not in (401, 403)


# ── Security headers ─────────────────────────────────────────────────


class TestSecurityHeaders:
    """All responses must include security headers."""

    def test_security_headers_present(self, client_no_key):
        resp = client_no_key.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "")


# ── Rate limiter unit tests ──────────────────────────────────────────


class TestRateLimiter:
    """In-memory rate limiter correctness."""

    def test_allows_within_limit(self):
        from app.core.auth import RateLimiter
        limiter = RateLimiter(per_minute=5, burst=5)
        # Simulate 5 requests — should all pass
        from unittest.mock import AsyncMock, MagicMock
        import asyncio

        request = MagicMock()
        request.client.host = "1.2.3.4"
        request.headers = {}

        for _ in range(5):
            asyncio.get_event_loop().run_until_complete(limiter(request))
        # 5th should have worked (no exception)

    def test_blocks_over_limit(self):
        from app.core.auth import RateLimiter
        from fastapi import HTTPException
        import asyncio
        from unittest.mock import MagicMock

        limiter = RateLimiter(per_minute=3, burst=3)
        request = MagicMock()
        request.client.host = "5.6.7.8"
        request.headers = {}

        for _ in range(3):
            asyncio.get_event_loop().run_until_complete(limiter(request))

        # 4th should be blocked
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(limiter(request))
        assert exc_info.value.status_code == 429
        assert "Retry" in exc_info.value.headers.get("Retry-After", "")

    def test_x_forwarded_for_respected(self):
        from app.core.auth import RateLimiter
        from unittest.mock import MagicMock

        limiter = RateLimiter(per_minute=60)
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "203.0.113.42, 10.0.0.1"}

        ip = limiter._client_ip(request)
        assert ip == "203.0.113.42"
