"""Source constants and mappings for watchlists."""
from typing import Literal

from app.models.notice import NoticeSource

# Source identifiers for watchlists
SourceType = Literal["TED", "BOSA"]

# Mapping from watchlist source identifier to notice.source value
# Must match NoticeSource enum values stored in ProcurementNotice.source
SOURCE_TO_NOTICE_SOURCE: dict[SourceType, str] = {
    "TED": NoticeSource.TED_EU.value,      # "TED_EU"
    "BOSA": NoticeSource.BOSA_EPROC.value,  # "BOSA_EPROC"
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
        List of notice.source values (e.g., ["TED_EU", "BOSA_EPROC"])
    """
    result = []
    for src in watchlist_sources:
        src_upper = src.strip().upper() if src else ""
        if src_upper in SOURCE_TO_NOTICE_SOURCE:
            notice_source = SOURCE_TO_NOTICE_SOURCE[src_upper]
            if notice_source not in result:
                result.append(notice_source)
    return result
