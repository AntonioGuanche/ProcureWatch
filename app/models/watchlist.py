"""Watchlist (alerts) model: saved search criteria for matching notices."""
import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.sources import DEFAULT_SOURCES


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
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="Comma-separated keywords")
    countries: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Comma-separated country codes")
    cpv_prefixes: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="Comma-separated CPV prefixes")
    sources: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON array of source identifiers",
    )
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    notify_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Email for alerts")
    nuts_prefixes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Comma-separated NUTS prefixes")
    value_min: Mapped[Optional[float]] = mapped_column(nullable=True, comment="Minimum estimated value (EUR)")
    value_max: Mapped[Optional[float]] = mapped_column(nullable=True, comment="Maximum estimated value (EUR)")
    last_refresh_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
