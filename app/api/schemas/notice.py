"""Notice schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, model_validator

from app.utils.cpv import normalize_cpv


class NoticeRead(BaseModel):
    """Schema for reading a notice. cpv_main_code is 8-digit; cpv is display (########-# or ########)."""

    id: str
    source: str
    source_id: str
    title: str
    buyer_name: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    cpv: Optional[str] = None  # Display format "########-#" or "########"
    cpv_main_code: Optional[str] = None  # 8-digit string
    procedure_type: Optional[str] = None
    published_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    url: str
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def normalize_cpv_output(self) -> "NoticeRead":
        """Ensure cpv_main_code is 8-digit and cpv is display format in API response."""
        raw = self.cpv_main_code or self.cpv
        if raw:
            cpv_8, _, display = normalize_cpv(raw)
            if cpv_8 is not None:
                object.__setattr__(self, "cpv_main_code", cpv_8)
            if display is not None:
                object.__setattr__(self, "cpv", display)
        return self


class NoticeListResponse(BaseModel):
    """Schema for paginated notice list."""

    total: int
    page: int
    page_size: int
    items: List[NoticeRead]


class NoticeDetailRead(BaseModel):
    """Stored publication detail (raw JSON + fetched_at)."""

    raw_json: Optional[str] = None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class NoticeLotRead(BaseModel):
    """Lot extracted from notice detail."""

    id: str
    notice_id: str
    lot_number: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    cpv_code: Optional[str] = None
    nuts_code: Optional[str] = None

    model_config = {"from_attributes": True}


class NoticeDocumentRead(BaseModel):
    """Document extracted from notice detail (includes pipeline status)."""

    id: str
    notice_id: str
    lot_id: Optional[str] = None
    title: Optional[str] = None
    url: str
    file_type: Optional[str] = None
    language: Optional[str] = None
    published_at: Optional[datetime] = None
    checksum: Optional[str] = None
    # Document pipeline
    local_path: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    sha256: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    download_status: Optional[str] = None
    download_error: Optional[str] = None
    extracted_at: Optional[datetime] = None
    extraction_status: Optional[str] = None
    extraction_error: Optional[str] = None

    model_config = {"from_attributes": True}


class NoticeDocumentTextRead(BaseModel):
    """Extracted text and metadata for a document (GET .../documents/{doc_id}/text)."""

    id: str
    notice_id: str
    title: Optional[str] = None
    extracted_text: Optional[str] = None
    extracted_at: Optional[datetime] = None
    extraction_status: Optional[str] = None
    extraction_error: Optional[str] = None

    model_config = {"from_attributes": True}


class NoticeLotListResponse(BaseModel):
    """Paginated lots for a notice."""

    total: int
    page: int
    page_size: int
    items: List[NoticeLotRead]


class NoticeDocumentListResponse(BaseModel):
    """Paginated documents for a notice."""

    total: int
    page: int
    page_size: int
    items: List[NoticeDocumentRead]
