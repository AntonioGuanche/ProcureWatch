"""Filter schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FilterBase(BaseModel):
    """Base filter schema."""

    name: str = Field(..., min_length=1, max_length=200)
    keywords: Optional[str] = Field(None, max_length=500)
    cpv_prefixes: Optional[str] = Field(None, max_length=200)
    countries: Optional[str] = Field(None, max_length=100)
    buyer_keywords: Optional[str] = Field(None, max_length=500)


class FilterCreate(FilterBase):
    """Schema for creating a filter."""

    pass


class FilterUpdate(BaseModel):
    """Schema for updating a filter."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    keywords: Optional[str] = Field(None, max_length=500)
    cpv_prefixes: Optional[str] = Field(None, max_length=200)
    countries: Optional[str] = Field(None, max_length=100)
    buyer_keywords: Optional[str] = Field(None, max_length=500)


class FilterRead(FilterBase):
    """Schema for reading a filter."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
