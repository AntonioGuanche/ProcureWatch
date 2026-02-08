"""E-Procurement connector: wraps BOSA official client for app use."""
import logging
from typing import Any, Optional

from app.connectors.bosa.client import _get_client
from app.connectors.bosa.official_client import OfficialEProcurementClient

logger = logging.getLogger(__name__)


def fetch_publication_workspace(publication_workspace_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch full publication workspace details from the Dos API.

    Args:
        publication_workspace_id: The publicationWorkspaceId from search results.

    Returns:
        JSON dict from the API, or None on 401/403/404 or if client is not official.
    """
    try:
        client, provider = _get_client()
        if not isinstance(client, OfficialEProcurementClient):
            logger.warning("Eproc connector: client is not OfficialEProcurementClient (provider=%s)", provider)
            return None
        return client.get_publication_workspace(publication_workspace_id)
    except Exception as e:
        logger.warning("fetch_publication_workspace(%s) failed: %s", publication_workspace_id, e)
        return None
