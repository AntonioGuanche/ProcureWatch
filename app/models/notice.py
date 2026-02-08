"""Belgian procurement notice model (BOSA / TED)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, func
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoticeSource(str, enum.Enum):
    """Source of the procurement notice."""

    BOSA_EPROC = "BOSA_EPROC"
    TED_EU = "TED_EU"


class ProcurementNotice(Base):
    """
    Belgian procurement notice (BOSA e-Procurement, TED EU).
    Table name: notices.
    """

    __tablename__ = "notices"

    # --- Primary key ---
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # --- Unique constraint: source_id (publicationWorkspaceId from BOSA) ---
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # NoticeSource enum value

    # --- Critical fields ---
    publication_workspace_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    procedure_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dossier_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cpv_main_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    cpv_additional_codes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # list of strings
    nuts_codes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # list of strings
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    insertion_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notice_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notice_sub_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    form_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    organisation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organisation_names: Mapped[Optional[dict[str, str]]] = mapped_column(JSON, nullable=True)  # multilingual dict
    publication_languages: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # list
    raw_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # full API response

    # --- Optional fields ---
    title: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    estimated_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)

    # --- BOSA enriched (URL, status, dossier, agreement, certificates, keywords) ---
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # PUBLISHED, ARCHIVED
    agreement_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dossier_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    required_accreditation: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dossier_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dossier_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agreement_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    keywords: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)  # e.g. ["keyword1", "keyword2"]
    migrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Indexes are defined via index=True on each mapped_column above.
    # UniqueConstraint on source_id is handled by unique=True on the column.
    __table_args__: tuple = ()


# --- Backward-compatibility alias ---
# Legacy code (CRUD, scripts, tests) imports "Notice". Point it to ProcurementNotice
# so all queries target the correct "notices" table.
Notice = ProcurementNotice

