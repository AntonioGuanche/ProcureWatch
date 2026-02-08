"""Filter model for user-defined procurement filters."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Filter(Base):
    """User-defined filter for procurement notices."""

    __tablename__ = "filters"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cpv_prefixes: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # comma-separated
    countries: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # comma-separated
    buyer_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )
