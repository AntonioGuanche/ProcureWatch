"""Smoke tests for admin router refactoring.

Verifies that the aggregator router correctly includes all sub-routers
and that all expected endpoints are registered.
"""
import pytest


@pytest.mark.unit
class TestAdminRouterAggregation:
    """Verify admin router includes all sub-routers."""

    def test_admin_router_has_routes(self):
        from app.api.routes.admin import router
        paths = [r.path for r in router.routes]
        # Should have routes from all sub-routers
        assert len(paths) >= 30, f"Expected 30+ routes, got {len(paths)}: {paths}"

    def test_import_endpoints_present(self):
        from app.api.routes.admin import router
        paths = {r.path for r in router.routes}
        assert "/admin/import" in paths or any("/import" in p for p in paths)

    def test_enrichment_endpoints_present(self):
        from app.api.routes.admin import router
        paths = {r.path for r in router.routes}
        assert any("match-watchlists" in p for p in paths)
        assert any("backfill" in p for p in paths)

    def test_bosa_endpoints_present(self):
        from app.api.routes.admin import router
        paths = {r.path for r in router.routes}
        assert any("bosa-diagnostics" in p for p in paths)

    def test_ted_endpoints_present(self):
        from app.api.routes.admin import router
        paths = {r.path for r in router.routes}
        assert any("fix-ted-cpv" in p for p in paths)

    def test_document_endpoints_present(self):
        from app.api.routes.admin import router
        paths = {r.path for r in router.routes}
        assert any("document-stats" in p for p in paths)

    def test_sub_routers_importable(self):
        """All sub-routers can be imported without error."""
        from app.api.routes.admin_import import router as r1
        from app.api.routes.admin_enrichment import router as r2
        from app.api.routes.admin_bosa import router as r3
        from app.api.routes.admin_ted import router as r4
        from app.api.routes.admin_documents import router as r5
        assert all(r is not None for r in [r1, r2, r3, r4, r5])

    def test_no_duplicate_paths(self):
        """No two endpoints should have the same method+path."""
        from app.api.routes.admin import router

        seen = set()
        for route in router.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    key = f"{method} {route.path}"
                    assert key not in seen, f"Duplicate route: {key}"
                    seen.add(key)
