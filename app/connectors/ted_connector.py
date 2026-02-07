"""TED (Tenders Electronic Daily) connector: app-level wrapper for TED search."""
import logging
from typing import Any

from connectors.ted.client import search_ted_notices as _search_ted_notices

logger = logging.getLogger(__name__)


def search_ted_notices(
    term: str,
    page: int = 1,
    page_size: int = 25,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Search TED notices via the configured TED client (official API or off).

    Args:
        term: Search keywords or expert query.
        page: Page number (1-based).
        page_size: Results per page.
        debug: If True, print request/response debug info.

    Returns:
        {"metadata": {...}, "json": raw API response, "notices": [...]}
        When TED is off, returns empty notices with metadata.
    """
    return _search_ted_notices(term=term, page=page, page_size=page_size, debug=debug)
