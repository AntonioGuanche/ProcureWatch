"""Backward-compat shim. Real models are in app.models.*."""
from app.models import (  # noqa: F401
    Filter,
    Notice,
    NoticeCpvAdditional,
    NoticeDetail,
    NoticeDocument,
    NoticeLot,
    ProcurementNotice,
    Watchlist,
    WatchlistMatch,
)
