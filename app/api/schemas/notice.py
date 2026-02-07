"""Notice schemas."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

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


class NoticeSearchItem(BaseModel):
    """Single notice row for GET /api/notices/search (Lovable table)."""

    id: str
    title: Optional[str] = None
    source: str
    cpv_main_code: Optional[str] = None
    organisation_names: Optional[Dict[str, str]] = None
    publication_date: Optional[str] = None  # ISO date YYYY-MM-DD
    deadline: Optional[str] = None  # ISO datetime or date
    reference_number: Optional[str] = None
    description: Optional[str] = None  # Truncated to 200 chars for list view

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


# --- Manual refresh (POST /api/notices/refresh) ---


class RefreshSearchCriteria(BaseModel):
    """Search criteria for notice refresh (BOSA + TED)."""

    keywords: Optional[str] = None
    cpv_codes: Optional[List[str]] = None
    publication_date_from: Optional[str] = None  # ISO date "YYYY-MM-DD"
    publication_date_to: Optional[str] = None
    page: Optional[int] = 1
    page_size: Optional[int] = 25


class RefreshRequest(BaseModel):
    """Body for POST /api/notices/refresh."""

    sources: Optional[List[str]] = None  # ["BOSA", "TED"] or omit for all
    search_criteria: Optional[RefreshSearchCriteria] = None


class RefreshSourceStats(BaseModel):
    """Per-source stats (bosa / ted)."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[dict] = []


class RefreshResponse(BaseModel):
    """Response for synchronous refresh (200) or completed job."""

    status: str = "success"
    stats: dict  # bosa, ted, total_created, total_updated
    duration_seconds: float = 0.0


class RefreshAcceptedResponse(BaseModel):
    """Response for async refresh (202 Accepted)."""

    status: str = "accepted"
    job_id: str
    message: str = "Refresh started in background. Poll GET /api/notices/refresh/jobs/{job_id} for result."


class RefreshJobStatusResponse(BaseModel):
    """Response for GET /api/notices/refresh/jobs/{job_id}."""

    job_id: str
    status: str  # pending | running | completed | failed
    result: Optional[RefreshResponse] = None
    created_at: Optional[datetime] = None


class NoticeStatsResponse(BaseModel):
    """Response for GET /api/notices/stats."""

    total_notices: int
    by_source: dict  # e.g. {"BOSA_EPROC": 805, "TED_EU": 442}
    last_import: Optional[str] = None  # ISO datetime of most recent updated_at
