"""CRUD operations for notices."""
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional


def list_notices(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    country: Optional[str] = None,
    cpv: Optional[str] = None,
    buyer: Optional[str] = None,
    deadline_from: Optional[datetime] = None,
    deadline_to: Optional[datetime] = None,
) -> Tuple[list[Notice], int]:
    """List notices with optional filtering. Returns (notices, total_count)."""
    query = db.query(Notice)

    # Search term in title (case-insensitive)
    if q:
        query = query.filter(Notice.title.ilike(f"%{q}%"))

    # Filter by country
    if country:
        query = query.filter(Notice.country == country.upper())

    # Filter by CPV (main code or additional codes)
    if cpv:
        # Remove dashes and normalize
        cpv_clean = cpv.replace("-", "")
        # Check main CPV code or additional codes via join
        query = query.outerjoin(
            NoticeCpvAdditional,
            Notice.id == NoticeCpvAdditional.notice_id
        ).filter(
            or_(
                Notice.cpv_main_code.like(f"{cpv_clean}%"),
                Notice.cpv.like(f"{cpv_clean}%"),  # Backward compatibility
                NoticeCpvAdditional.cpv_code.like(f"{cpv_clean}%")
            )
        ).distinct()

    # Filter by buyer name
    if buyer:
        query = query.filter(Notice.buyer_name.ilike(f"%{buyer}%"))

    # Filter by deadline range
    if deadline_from:
        query = query.filter(Notice.deadline_at >= deadline_from)
    if deadline_to:
        query = query.filter(Notice.deadline_at <= deadline_to)

    # Get total count before pagination
    total = query.count()

    # Order by published_at descending (newest first)
    query = query.order_by(Notice.published_at.desc().nulls_last())

    # Apply pagination
    notices = query.offset(offset).limit(limit).all()

    return notices, total


def get_notice_by_id(db: Session, notice_id: str) -> Optional[Notice]:
    """Get a notice by ID."""
    return db.query(Notice).filter(Notice.id == notice_id).first()
