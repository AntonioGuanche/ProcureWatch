"""Stored publication detail (raw JSON) for a notice."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NoticeDetail(Base):
    """Detail storage: raw JSON from publication detail API."""

    __tablename__ = "notice_details"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    notice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
