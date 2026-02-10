"""User favorites: bookmark notices for quick access."""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserFavorite(Base):
    """A user's bookmarked notice."""

    __tablename__ = "user_favorites"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    notice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "notice_id", name="uq_user_favorite"),
    )
