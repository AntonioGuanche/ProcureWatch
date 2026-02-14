"""All SQLAlchemy models — single source of truth.

Import models from here:
    from app.models import ProcurementNotice, Watchlist, NoticeLot, ...
    from app.models.notice import Notice  # backward-compat alias for ProcurementNotice
"""
from app.models.base import Base
from app.models.filter import Filter
from app.models.notice import Notice, NoticeSource, ProcurementNotice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.models.notice_detail import NoticeDetail
from app.models.notice_document import NoticeDocument
from app.models.notice_lot import NoticeLot
from app.models.watchlist import Watchlist
from app.models.watchlist_match import WatchlistMatch
from app.models.import_run import ImportRun
from app.models.translation_cache import TranslationCache

__all__ = [
    "Base",
    "Filter",
    "Notice",
    "NoticeSource",
    "NoticeCpvAdditional",
    "NoticeDetail",
    "NoticeDocument",
    "NoticeLot",
    "ProcurementNotice",
    "Watchlist",
    "ImportRun",
    "WatchlistMatch",
    "TranslationCache",
]
