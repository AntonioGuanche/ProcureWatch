"""Watchlist match model: stores which notices match which watchlists."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WatchlistMatch(Base):
    """Stores matches between watchlists and notices with explanation."""

    __tablename__ = "watchlist_matches"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    watchlist_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    matched_on: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Explanation of why this notice matched (e.g., 'keyword: solar, CPV: 45')",
    )
    relevance_score: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="Relevance score 0-100 based on match quality",
    )
    matched_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("watchlist_id", "notice_id", name="uq_watchlist_match"),
    )
