"""Notice schemas."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, model_validator

from app.utils.cpv import normalize_cpv


class NoticeRead(BaseModel):
    """Schema for reading a notice (matches ProcurementNotice model)."""

    id: str
    source: str
    source_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    organisation_names: Optional[Dict[str, str]] = None
    nuts_codes: Optional[List[str]] = None
    cpv_main_code: Optional[str] = None
    notice_type: Optional[str] = None
    notice_sub_type: Optional[str] = None
    form_type: Optional[str] = None
    publication_date: Optional[date] = None
    deadline: Optional[datetime] = None
    estimated_value: Optional[Any] = None
    url: Optional[str] = None
    status: Optional[str] = None
    reference_number: Optional[str] = None
    # CAN (Contract Award Notice) fields
    award_winner_name: Optional[str] = None
    award_value: Optional[Any] = None
    award_date: Optional[date] = None
    number_tenders_received: Optional[int] = None
    # AI summary
    ai_summary: Optional[str] = None
    ai_summary_lang: Optional[str] = None
    ai_summary_generated_at: Optional[datetime] = None
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def normalize_cpv_output(self) -> "NoticeRead":
        """Ensure cpv_main_code is 8-digit."""
        raw = self.cpv_main_code
        if raw:
            cpv_8, _, display = normalize_cpv(raw)
            if cpv_8 is not None:
                object.__setattr__(self, "cpv_main_code", cpv_8)
        return self


class NoticeListResponse(BaseModel):
    """Schema for paginated notice list."""

    total: int
    page: int
    page_size: int
    items: List[NoticeRead]


class NoticeSearchItem(BaseModel):
    """Single notice row for GET /api/notices/search (frontend table/card)."""

    id: str
    title: Optional[str] = None
    source: str
    cpv_main_code: Optional[str] = None
    nuts_codes: Optional[List[str]] = None
    organisation_names: Optional[Dict[str, str]] = None
    publication_date: Optional[str] = None
    deadline: Optional[str] = None
    reference_number: Optional[str] = None
    description: Optional[str] = None
    notice_type: Optional[str] = None
    form_type: Optional[str] = None
    estimated_value: Optional[float] = None
    url: Optional[str] = None
    status: Optional[str] = None

    model_config = {"from_attributes": True}


class NoticeSearchResponse(BaseModel):
    """Paginated search result for GET /api/notices/search."""

    items: List[NoticeSearchItem]
    total: int
    page: int
    page_size: int
    total_pages: int


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
    """Extracted text and metadata for a document."""

    id: str
    notice_id: str
    title: Optional[str] = None
    extracted_text: Optional[str] = None
    extracted_at: Optional[datetime] = None
    extraction_status: Optional[str] = None
    extraction_error: Optional[str] = None

    model_config = {"from_attributes": True}


class NoticeLotListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[NoticeLotRead]


class NoticeDocumentListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[NoticeDocumentRead]


class RefreshSearchCriteria(BaseModel):
    keywords: Optional[str] = None
    cpv_codes: Optional[List[str]] = None
    publication_date_from: Optional[str] = None
    publication_date_to: Optional[str] = None
    page: Optional[int] = 1
    page_size: Optional[int] = 25


class RefreshRequest(BaseModel):
    sources: Optional[List[str]] = None
    search_criteria: Optional[RefreshSearchCriteria] = None


class RefreshSourceStats(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[dict] = []


class RefreshResponse(BaseModel):
    status: str = "success"
    stats: dict
    duration_seconds: float = 0.0


class RefreshAcceptedResponse(BaseModel):
    status: str = "accepted"
    job_id: str
    message: str = "Refresh started in background. Poll GET /api/notices/refresh/jobs/{job_id} for result."


class RefreshJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[RefreshResponse] = None
    created_at: Optional[datetime] = None


class NoticeStatsResponse(BaseModel):
    total_notices: int
    by_source: dict
    last_import: Optional[str] = None
