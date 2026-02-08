"""Lot extracted from a notice's publication detail."""
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoticeLot(Base):
    """Lot: subdivision of a notice (e.g. by CPV or geography)."""

    __tablename__ = "notice_lots"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    notice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
    )
    lot_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cpv_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nuts_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
