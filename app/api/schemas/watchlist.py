"""Watchlist (alerts) schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WatchlistBase(BaseModel):
    """Base fields for watchlist."""

    name: str = Field(..., min_length=1, max_length=255)
    is_enabled: bool = True
    term: Optional[str] = Field(None, max_length=255)
    cpv_prefix: Optional[str] = Field(None, max_length=20)
    buyer_contains: Optional[str] = Field(None, max_length=255)
    procedure_type: Optional[str] = Field(None, max_length=100)
    country: str = Field(default="BE", max_length=2)
    language: Optional[str] = Field(None, max_length=2)
    notify_email: Optional[str] = Field(None, max_length=255)


class WatchlistCreate(WatchlistBase):
    """Schema for creating a watchlist."""

    pass


class WatchlistUpdate(BaseModel):
    """Schema for partial update of a watchlist."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_enabled: Optional[bool] = None
    term: Optional[str] = Field(None, max_length=255)
    cpv_prefix: Optional[str] = Field(None, max_length=20)
    buyer_contains: Optional[str] = Field(None, max_length=255)
    procedure_type: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)
    language: Optional[str] = Field(None, max_length=2)
    notify_email: Optional[str] = Field(None, max_length=255)


class WatchlistRead(WatchlistBase):
    """Schema for reading a watchlist."""

    id: str
    last_refresh_at: Optional[datetime] = None
    last_refresh_status: Optional[str] = None
    last_notified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WatchlistListResponse(BaseModel):
    """Paginated list of watchlists."""

    total: int
    page: int
    page_size: int
    items: list[WatchlistRead]
