"""Watchlist (alerts) schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.notice import NoticeRead
from app.utils.sources import DEFAULT_SOURCES, VALID_SOURCES


class WatchlistBase(BaseModel):
    """Base fields for watchlist."""

    name: str = Field(..., min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list, description="Keywords to match in title/description")
    countries: list[str] = Field(default_factory=list, description="Country codes (ISO2) to filter by")
    cpv_prefixes: list[str] = Field(default_factory=list, description="CPV code prefixes to match")
    sources: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SOURCES),
        description="Source identifiers to filter by (TED, BOSA, or both)",
    )

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: list[str]) -> list[str]:
        """Validate that sources are valid identifiers."""
        if not v:
            return list(DEFAULT_SOURCES)
        invalid = set(v) - VALID_SOURCES
        if invalid:
            raise ValueError(f"Invalid source(s): {invalid}. Valid sources are: {VALID_SOURCES}")
        return v


class WatchlistCreate(WatchlistBase):
    """Schema for creating a watchlist."""

    sources: Optional[list[str]] = Field(
        default=None,
        description="Source identifiers (TED, BOSA, or both). Defaults to both if omitted.",
    )

    @field_validator("sources", mode="before")
    @classmethod
    def default_sources(cls, v: Optional[list[str]]) -> list[str]:
        """Default to both sources if not provided."""
        if v is None:
            return list(DEFAULT_SOURCES)
        return v


class WatchlistUpdate(BaseModel):
    """Schema for partial update of a watchlist."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    keywords: Optional[list[str]] = None
    countries: Optional[list[str]] = None
    cpv_prefixes: Optional[list[str]] = None
    sources: Optional[list[str]] = None

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validate that sources are valid identifiers."""
        if v is None:
            return None
        if not v:
            return list(DEFAULT_SOURCES)
        invalid = set(v) - VALID_SOURCES
        if invalid:
            raise ValueError(f"Invalid source(s): {invalid}. Valid sources are: {VALID_SOURCES}")
        return v


class WatchlistRead(WatchlistBase):
    """Schema for reading a watchlist."""

    id: str
    last_refresh_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WatchlistListResponse(BaseModel):
    """Paginated list of watchlists."""

    total: int
    page: int
    page_size: int
    items: list[WatchlistRead]


class WatchlistMatchRead(BaseModel):
    """Schema for a watchlist match with explanation."""

    notice: NoticeRead
    matched_on: str = Field(..., description="Explanation of why this notice matched")


class WatchlistMatchesResponse(BaseModel):
    """Paginated list of matched notices for a watchlist."""

    total: int
    page: int
    page_size: int
    items: list[WatchlistMatchRead]
