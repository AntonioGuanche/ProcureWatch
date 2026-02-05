"""Notice CPV additional codes model."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NoticeCpvAdditional(Base):
    """Additional CPV codes for notices."""

    __tablename__ = "notice_cpv_additional"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
    )
    cpv_code: Mapped[str] = mapped_column(String(20), nullable=False)
