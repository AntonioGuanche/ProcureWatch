"""Notice model for procurement opportunities."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notice(Base):
    """Legacy notice model (old schema). Table renamed to notices_old to avoid conflict with ProcurementNotice."""

    __tablename__ = "notices_old"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    buyer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    cpv: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Main CPV code (kept for backward compatibility)
    cpv_main_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Main CPV code (alias)
    procedure_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # TEXT for SQLite, JSONB in Postgres later
    first_seen_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_notice_old_source_source_id"),
        Index("ix_notices_old_published_at", "published_at"),
        Index("ix_notices_old_deadline_at", "deadline_at"),
        Index("ix_notices_old_cpv", "cpv"),
        Index("ix_notices_old_cpv_main_code", "cpv_main_code"),
        {"extend_existing": True},
    )
