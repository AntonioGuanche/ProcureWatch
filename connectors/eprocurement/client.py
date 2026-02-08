"""Backward-compat shim → app.connectors.bosa.client (Phase 2)."""
from app.connectors.bosa.client import *  # noqa: F401,F403
from app.connectors.bosa.client import _get_client, reset_client, search_publications, get_publication_detail, get_cpv_label
