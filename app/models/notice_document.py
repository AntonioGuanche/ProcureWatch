"""Document extracted from a notice's publication detail."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoticeDocument(Base):
    """Document: file or link associated with a notice (optionally a lot)."""

    __tablename__ = "notice_documents"

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
    lot_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("notice_lots.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Document pipeline: download
    local_path: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    download_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # ok|failed
    download_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Document pipeline: text extraction (PDFs)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    extraction_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # ok|skipped|failed
    extraction_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Document pipeline: AI analysis (Phase 2)
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_analysis_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
