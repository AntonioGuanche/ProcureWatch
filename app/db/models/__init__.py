"""Database models.
Notice table: use app.models.notice.ProcurementNotice ('notices'). Old app.db.models.notice.Notice
is disabled (maps to notices_old) to avoid table conflict.
"""
from app.db.models.filter import Filter
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.models.notice_detail import NoticeDetail
from app.db.models.notice_document import NoticeDocument
from app.db.models.notice_lot import NoticeLot
from app.db.models.watchlist import Watchlist
from app.db.models.watchlist_match import WatchlistMatch

__all__ = [
    "Filter",
    "NoticeCpvAdditional",
    "NoticeDetail",
    "NoticeDocument",
    "NoticeLot",
    "Watchlist",
    "WatchlistMatch",
]
