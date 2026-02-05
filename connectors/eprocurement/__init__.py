"""Belgian e-Procurement connectors (official API + Playwright fallback)."""
from connectors.eprocurement.client import (
    get_cpv_label,
    get_publication_detail,
    search_publications,
)

__all__ = [
    "search_publications",
    "get_publication_detail",
    "get_cpv_label",
]
