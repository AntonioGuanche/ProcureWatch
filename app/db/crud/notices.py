"""CRUD operations for notices."""
from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy import cast, or_, text, String
from sqlalchemy.orm import Session

from app.models.notice import Notice  # alias for ProcurementNotice
from app.models.notice_cpv_additional import NoticeCpvAdditional


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
    sources: Optional[list[str]] = None,
) -> Tuple[list[Notice], int]:
    """List notices with optional filtering. Returns (notices, total_count).
    sources: optional list of source identifiers (e.g. TED, BOSA); when provided,
    filters Notice.source via SOURCE_TO_NOTICE_SOURCE.
    """
    from app.utils.sources import get_notice_sources_for_watchlist

    query = db.query(Notice)

    # Filter by source(s): TED -> TED_EU, BOSA -> BOSA_EPROC
    if sources:
        notice_sources = get_notice_sources_for_watchlist(
            [s.strip() for s in sources if s and str(s).strip()]
        )
        if notice_sources:
            query = query.filter(Notice.source.in_(notice_sources))

    # Search term in title (case-insensitive)
    if q:
        query = query.filter(Notice.title.ilike(f"%{q}%"))

    # Filter by NUTS code prefix (replaces legacy country filter)
    if country:
        # NUTS codes start with 2-letter country code (e.g. BE, FR)
        # ProcurementNotice stores nuts_codes as JSON array
        country_upper = country.upper()
        query = query.filter(
            cast(Notice.nuts_codes, String).ilike(f'%"{country_upper}%')
        )

    # Filter by CPV (main code or additional codes)
    if cpv:
        cpv_clean = cpv.replace("-", "")
        query = query.outerjoin(
            NoticeCpvAdditional,
            Notice.id == NoticeCpvAdditional.notice_id,
        ).filter(
            or_(
                Notice.cpv_main_code.like(f"{cpv_clean}%"),
                NoticeCpvAdditional.cpv_code.like(f"{cpv_clean}%"),
            )
        ).distinct()

    # Filter by buyer/organisation name (JSON field: organisation_names)
    if buyer:
        query = query.filter(
            cast(Notice.organisation_names, String).ilike(f"%{buyer}%")
        )

    # Filter by deadline range
    if deadline_from:
        query = query.filter(Notice.deadline >= deadline_from)
    if deadline_to:
        query = query.filter(Notice.deadline <= deadline_to)

    # Get total count before pagination
    total = query.count()

    # Order by publication_date descending (newest first)
    query = query.order_by(Notice.publication_date.desc().nulls_last())

    # Apply pagination
    notices = query.offset(offset).limit(limit).all()

    return notices, total


def get_notice_by_id(db: Session, notice_id: str) -> Optional[Notice]:
    """Get a notice by ID."""
    return db.query(Notice).filter(Notice.id == notice_id).first()


def get_notice_stats(db: Session) -> dict[str, Any]:
    """
    Aggregate stats for notices table (source, updated_at columns).
    Returns total_notices, by_source (e.g. BOSA_EPROC, TED_EU), last_import (ISO datetime).
    Uses raw SQL to avoid model ambiguity.
    """
    total_row = db.execute(text("SELECT COUNT(*) FROM notices")).scalar()
    total = int(total_row) if total_row is not None else 0
    rows = db.execute(
        text("SELECT source, COUNT(*) FROM notices GROUP BY source")
    ).fetchall()
    by_source = {str(row[0]): int(row[1]) for row in rows}
    last_row = db.execute(text("SELECT MAX(updated_at) FROM notices")).scalar()
    last_import = None
    if last_row is not None:
        last_import = (
            last_row.isoformat() if hasattr(last_row, "isoformat") else str(last_row)
        )
    return {
        "total_notices": total,
        "by_source": by_source,
        "last_import": last_import,
    }
