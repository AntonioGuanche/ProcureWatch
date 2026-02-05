"""Watchlist (alerts) model: saved search criteria for matching notices."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Watchlist(Base):
    """
    Watchlist (alert): name, enabled flag, and optional filters.
    A match occurs when a notice satisfies all non-null filters.
    No user association for now (no auth).
    """

    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    term: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cpv_prefix: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    buyer_contains: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    procedure_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="BE")
    language: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    last_refresh_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_refresh_status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notify_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
