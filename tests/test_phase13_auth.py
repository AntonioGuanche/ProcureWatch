"""Phase 13: Auth, admin key protection, rate limiting, security headers."""
import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# -- Fixtures ----------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_test_db(tmp_path):
    """Ensure tests use a temp SQLite DB with all tables created."""
    db_path = tmp_path / "test_auth.db"
    db_url = f"sqlite:///{db_path}"
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        yield


def _make_client(admin_key: str = ""):
    """Build a fresh TestClient with given ADMIN_API_KEY."""
    env = {"ADMIN_API_KEY": admin_key}
    with patch.dict(os.environ, env):
        from importlib import reload
        import app.core.config as cfg_mod;            reload(cfg_mod)
        import app.core.auth as auth_mod;              reload(auth_mod)
        import app.core.security as sec_mod;           reload(sec_mod)
        import app.db.session as sess_mod;             reload(sess_mod)
        import app.api.routes.admin as admin_mod;      reload(admin_mod)
        import app.api.routes.notices as notices_mod;   reload(notices_mod)
        import app.api.routes.filters as filters_mod;   reload(filters_mod)
        import app.api.routes.auth as auth_r_mod;      reload(auth_r_mod)
        try:
            import app.api.routes.watchlists_mvp as wl_mod; reload(wl_mod)
        except Exception:
            pass
        import app.main as main_mod; reload(main_mod)

        # Create all tables
        from app.db.session import engine
        from app.models.notice import Base
        Base.metadata.create_all(bind=engine)

        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS import_runs (
                    id TEXT PRIMARY KEY,
                    source TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_count INTEGER DEFAULT 0,
                    updated_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    errors_json TEXT,
                    search_criteria_json TEXT
                )
            """))
            conn.commit()

        return TestClient(main_mod.app)


@pytest.fixture
def client_protected():
    return _make_client(admin_key="test-secret-key-123")


@pytest.fixture
def client_dev():
    return _make_client(admin_key="")


# -- Admin key tests ---------------------------------------------------


class TestAdminKeyProtection:

    def test_admin_no_key_returns_401(self, client_protected):
        resp = client_protected.get("/api/admin/import-runs?limit=1")
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    def test_admin_wrong_key_returns_403(self, client_protected):
        resp = client_protected.get(
            "/api/admin/import-runs?limit=1",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_admin_correct_key_passes(self, client_protected):
        resp = client_protected.get(
            "/api/admin/import-runs?limit=1",
            headers={"X-Admin-Key": "test-secret-key-123"},
        )
        assert resp.status_code == 200

    def test_admin_dev_mode_open(self, client_dev):
        resp = client_dev.get("/api/admin/import-runs?limit=1")
        assert resp.status_code == 200


# -- Public endpoints remain open --------------------------------------


class TestPublicEndpointsOpen:

    def test_health_open(self, client_protected):
        resp = client_protected.get("/health")
        assert resp.status_code == 200

    def test_search_open(self, client_protected):
        resp = client_protected.get("/api/notices/search?q=test&page_size=1")
        assert resp.status_code == 200

    def test_facets_open(self, client_protected):
        resp = client_protected.get("/api/notices/facets")
        assert resp.status_code == 200


# -- Security headers --------------------------------------------------


class TestSecurityHeaders:

    def test_security_headers_present(self, client_protected):
        resp = client_protected.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "")


# -- Rate limiter unit tests -------------------------------------------


class TestRateLimiter:

    def _make_request(self, ip="1.2.3.4"):
        request = MagicMock()
        request.client.host = ip
        request.headers = {}
        return request

    def test_allows_within_limit(self):
        from app.core.auth import RateLimiter
        limiter = RateLimiter(per_minute=5, burst=5)
        request = self._make_request()
        for _ in range(5):
            asyncio.run(limiter(request))

    def test_blocks_over_limit(self):
        from app.core.auth import RateLimiter
        from fastapi import HTTPException
        limiter = RateLimiter(per_minute=3, burst=3)
        request = self._make_request(ip="5.6.7.8")
        for _ in range(3):
            asyncio.run(limiter(request))
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(limiter(request))
        assert exc_info.value.status_code == 429
        retry_after = exc_info.value.headers.get("Retry-After", "")
        assert retry_after.isdigit(), f"Expected numeric Retry-After, got: {retry_after}"

    def test_different_ips_independent(self):
        from app.core.auth import RateLimiter
        from fastapi import HTTPException
        limiter = RateLimiter(per_minute=2, burst=2)
        req_a = self._make_request(ip="10.0.0.1")
        req_b = self._make_request(ip="10.0.0.2")
        for _ in range(2):
            asyncio.run(limiter(req_a))
        with pytest.raises(HTTPException):
            asyncio.run(limiter(req_a))
        asyncio.run(limiter(req_b))  # should pass

    def test_x_forwarded_for_respected(self):
        from app.core.auth import RateLimiter
        limiter = RateLimiter(per_minute=60)
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"x-forwarded-for": "203.0.113.42, 10.0.0.1"}
        assert limiter._client_ip(request) == "203.0.113.42"
