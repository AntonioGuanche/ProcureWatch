"""Import run: tracks each data ingestion run (daily import stats)."""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ImportRun(Base):
    """One row per import execution — source, counts, timing, errors."""

    __tablename__ = "import_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
        default=func.now(),
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    errors_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    search_criteria_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
