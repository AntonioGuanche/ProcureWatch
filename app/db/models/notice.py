"""Backward-compat shim. Real model is in app.models.notice."""
from app.models.notice import Notice, NoticeSource, ProcurementNotice  # noqa: F401
