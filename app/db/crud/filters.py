"""CRUD operations for filters."""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.schemas.filter import FilterCreate, FilterUpdate
from app.models.filter import Filter


def create_filter(db: Session, data: FilterCreate) -> Filter:
    """Create a new filter."""
    db_filter = Filter(**data.model_dump())
    db.add(db_filter)
    db.commit()
    db.refresh(db_filter)
    return db_filter


def list_filters(db: Session, limit: int = 100, offset: int = 0) -> list[Filter]:
    """List filters with pagination."""
    return db.query(Filter).offset(offset).limit(limit).all()


def get_filter(db: Session, filter_id: str) -> Optional[Filter]:
    """Get a filter by ID."""
    return db.query(Filter).filter(Filter.id == filter_id).first()


def update_filter(db: Session, filter_id: str, data: FilterUpdate) -> Optional[Filter]:
    """Update a filter."""
    db_filter = get_filter(db, filter_id)
    if not db_filter:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_filter, key, value)

    db.commit()
    db.refresh(db_filter)
    return db_filter


def delete_filter(db: Session, filter_id: str) -> bool:
    """Delete a filter."""
    db_filter = get_filter(db, filter_id)
    if not db_filter:
        return False

    db.delete(db_filter)
    db.commit()
    return True
