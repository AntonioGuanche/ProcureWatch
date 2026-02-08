"""Backward-compat shim → app.connectors.ted.openapi_discovery (Phase 2)."""
from app.connectors.ted.openapi_discovery import *  # noqa: F401,F403
from app.connectors.ted.openapi_discovery import TEDDiscoveryError, load_or_discover_endpoints
