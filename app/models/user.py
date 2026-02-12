"""User model for authentication."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """Application user: email + hashed password."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )

    # ── Company identity ──
    company_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    vat_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, unique=True, index=True,
        comment="VAT number, e.g. BE0123456789",
    )
    nace_codes: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Comma-separated NACE codes (auto from BCE)",
    )

    # ── Location ──
    address: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    postal_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(5), nullable=True, server_default="BE",
        comment="ISO 3166-1 alpha-2",
    )
    latitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )

    # ── Subscription / billing ──
    plan: Mapped[str] = mapped_column(
        String(20), default="free", server_default="free", nullable=False,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True,
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    subscription_status: Mapped[str] = mapped_column(
        String(30), default="none", server_default="none", nullable=False,
    )
    subscription_ends_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, comment="End of current billing period (UTC)",
    )
    # --- AI usage tracking ---
    ai_usage_count: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False,
        comment="AI summaries used this billing period",
    )
    ai_usage_reset_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, comment="Last AI usage counter reset (UTC)",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), server_default=func.now(),
    )
