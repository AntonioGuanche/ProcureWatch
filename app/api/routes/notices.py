"""Notice endpoints."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas.notice import (
    NoticeDetailRead,
    NoticeDocumentListResponse,
    NoticeDocumentRead,
    NoticeDocumentTextRead,
    NoticeListResponse,
    NoticeLotListResponse,
    NoticeLotRead,
    NoticeRead,
)
from app.db.crud.notice_detail import (
    get_notice_detail_by_notice_id,
    get_document_by_notice_and_id,
    list_documents_by_notice_id,
    list_lots_by_notice_id,
)
from app.db.crud.notices import get_notice_by_id, list_notices
from app.db.session import get_db

router = APIRouter(prefix="/notices", tags=["notices"])


@router.get("", response_model=NoticeListResponse)
async def get_notices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    term: Optional[str] = Query(None, alias="q", description="Search term in title"),
    cpv: Optional[str] = Query(None, description="Filter by CPV code (main or additional)"),
    buyer: Optional[str] = Query(None, description="Filter by buyer name"),
    deadline_from: Optional[datetime] = Query(None, description="Filter by deadline from (ISO datetime)"),
    deadline_to: Optional[datetime] = Query(None, description="Filter by deadline to (ISO datetime)"),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """List notices with pagination and optional filtering."""
    offset = (page - 1) * page_size
    
    notices, total = list_notices(
        db,
        limit=page_size,
        offset=offset,
        q=term,
        cpv=cpv,
        buyer=buyer,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )
    
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=notices,
    )


@router.get("/{notice_id}/detail", response_model=NoticeDetailRead)
async def get_notice_detail(
    notice_id: str,
    db: Session = Depends(get_db),
) -> NoticeDetailRead:
    """Get stored publication detail (raw JSON + fetched_at). 404 if not present."""
    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    detail = get_notice_detail_by_notice_id(db, notice_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found for this notice")
    return detail


@router.get("/{notice_id}/lots", response_model=NoticeLotListResponse)
async def get_notice_lots(
    notice_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> NoticeLotListResponse:
    """Get paginated lots for a notice."""
    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    offset = (page - 1) * page_size
    items, total = list_lots_by_notice_id(db, notice_id, limit=page_size, offset=offset)
    return NoticeLotListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{notice_id}/documents", response_model=NoticeDocumentListResponse)
async def get_notice_documents(
    notice_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> NoticeDocumentListResponse:
    """Get paginated documents for a notice (includes pipeline status and local_path)."""
    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    offset = (page - 1) * page_size
    items, total = list_documents_by_notice_id(db, notice_id, limit=page_size, offset=offset)
    return NoticeDocumentListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{notice_id}/documents/{document_id}/text", response_model=NoticeDocumentTextRead)
async def get_notice_document_text(
    notice_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> NoticeDocumentTextRead:
    """Get extracted text for a document. 404 if document not found or no text stored."""
    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    doc = get_document_by_notice_and_id(db, notice_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.extracted_text is None:
        raise HTTPException(status_code=404, detail="No extracted text for this document")
    return doc


@router.get("/{notice_id}", response_model=NoticeRead)
async def get_notice(
    notice_id: str,
    db: Session = Depends(get_db),
) -> NoticeRead:
    """Get a notice by ID."""
    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    return notice
