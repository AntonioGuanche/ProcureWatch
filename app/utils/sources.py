"""Source constants and mappings for watchlists."""
from typing import Literal

# Source identifiers for watchlists
SourceType = Literal["TED", "BOSA"]

# Mapping from watchlist source identifier to notice.source value
SOURCE_TO_NOTICE_SOURCE: dict[SourceType, str] = {
    "TED": "ted.europa.eu",
    "BOSA": "bosa.eprocurement",
}

# Valid source values
VALID_SOURCES: set[SourceType] = {"TED", "BOSA"}

# Default sources for watchlists
DEFAULT_SOURCES: list[SourceType] = ["TED", "BOSA"]


def get_notice_sources_for_watchlist(watchlist_sources: list[str]) -> list[str]:
    """
    Convert watchlist source identifiers to notice.source values.
    
    Args:
        watchlist_sources: List of source identifiers (e.g., ["TED", "BOSA"])
    
    Returns:
        List of notice.source values (e.g., ["ted.europa.eu", "bosa.eprocurement"])
    """
    result = []
    for src in watchlist_sources:
        if src in SOURCE_TO_NOTICE_SOURCE:
            notice_source = SOURCE_TO_NOTICE_SOURCE[src]
            if notice_source not in result:
                result.append(notice_source)
    return result
