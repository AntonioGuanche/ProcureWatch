"""Filter endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.filter import FilterCreate, FilterRead, FilterUpdate
from app.db.crud.filters import (
    create_filter,
    delete_filter,
    get_filter,
    list_filters,
    update_filter,
)
from app.db.session import get_db

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("", response_model=List[FilterRead])
async def get_filters(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[FilterRead]:
    """List all filters."""
    filters = list_filters(db, limit=limit, offset=offset)
    return filters


@router.post("", response_model=FilterRead, status_code=201)
async def create_new_filter(
    data: FilterCreate,
    db: Session = Depends(get_db),
) -> FilterRead:
    """Create a new filter."""
    filter_obj = create_filter(db, data)
    return filter_obj


@router.get("/{filter_id}", response_model=FilterRead)
async def get_filter_by_id(
    filter_id: str,
    db: Session = Depends(get_db),
) -> FilterRead:
    """Get a filter by ID."""
    filter_obj = get_filter(db, filter_id)
    if not filter_obj:
        raise HTTPException(status_code=404, detail="Filter not found")
    return filter_obj


@router.patch("/{filter_id}", response_model=FilterRead)
async def update_filter_by_id(
    filter_id: str,
    data: FilterUpdate,
    db: Session = Depends(get_db),
) -> FilterRead:
    """Update a filter."""
    filter_obj = update_filter(db, filter_id, data)
    if not filter_obj:
        raise HTTPException(status_code=404, detail="Filter not found")
    return filter_obj


@router.delete("/{filter_id}", status_code=204)
async def delete_filter_by_id(
    filter_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a filter."""
    success = delete_filter(db, filter_id)
    if not success:
        raise HTTPException(status_code=404, detail="Filter not found")
