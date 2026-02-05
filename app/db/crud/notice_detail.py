"""CRUD for notice_details, notice_lots, notice_documents."""
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.notice_detail import NoticeDetail
from app.db.models.notice_document import NoticeDocument
from app.db.models.notice_lot import NoticeLot


def get_notice_detail_by_notice_id(db: Session, notice_id: str) -> Optional[NoticeDetail]:
    """Get stored detail for a notice (raw_json + fetched_at)."""
    return db.query(NoticeDetail).filter(NoticeDetail.notice_id == notice_id).first()


def upsert_notice_detail(
    db: Session,
    notice_id: str,
    source: str,
    source_id: str,
    raw_json: Optional[str] = None,
) -> NoticeDetail:
    """Insert or update notice_detail for a notice."""
    existing = get_notice_detail_by_notice_id(db, notice_id)
    if existing:
        existing.source = source
        existing.source_id = source_id
        existing.raw_json = raw_json
        existing.fetched_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    row = NoticeDetail(
        notice_id=notice_id,
        source=source,
        source_id=source_id,
        raw_json=raw_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_lots_by_notice_id(
    db: Session,
    notice_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[NoticeLot], int]:
    """List lots for a notice with pagination. Returns (items, total)."""
    query = db.query(NoticeLot).filter(NoticeLot.notice_id == notice_id)
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return items, total


def list_documents_by_notice_id(
    db: Session,
    notice_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[NoticeDocument], int]:
    """List documents for a notice with pagination. Returns (items, total)."""
    query = db.query(NoticeDocument).filter(NoticeDocument.notice_id == notice_id)
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return items, total


def upsert_lots_for_notice(db: Session, notice_id: str, lots: list[dict[str, Any]]) -> int:
    """Delete existing lots for notice and insert new ones. Returns count inserted."""
    db.query(NoticeLot).filter(NoticeLot.notice_id == notice_id).delete()
    count = 0
    for lot in lots:
        row = NoticeLot(
            notice_id=notice_id,
            lot_number=lot.get("lot_number"),
            title=lot.get("title"),
            description=lot.get("description"),
            cpv_code=lot.get("cpv_code"),
            nuts_code=lot.get("nuts_code"),
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def upsert_documents_for_notice(
    db: Session,
    notice_id: str,
    documents: list[dict[str, Any]],
    lot_number_to_id: dict[str, str],
) -> int:
    """Delete existing documents for notice and insert new ones. lot_number_to_id maps lot_number -> notice_lots.id. Returns count inserted."""
    db.query(NoticeDocument).filter(NoticeDocument.notice_id == notice_id).delete()
    count = 0
    for doc in documents:
        lot_number = doc.get("lot_number")
        lot_id = lot_number_to_id.get(lot_number) if lot_number else None
        published_at = doc.get("published_at")
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                published_at = None
        elif not isinstance(published_at, datetime):
            published_at = None
        row = NoticeDocument(
            notice_id=notice_id,
            lot_id=lot_id,
            title=doc.get("title"),
            url=doc.get("url") or "",
            file_type=doc.get("file_type"),
            language=doc.get("language"),
            published_at=published_at,
            checksum=doc.get("checksum"),
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def get_lot_ids_by_lot_number(db: Session, notice_id: str, lot_numbers: list[str]) -> dict[str, str]:
    """Return mapping lot_number -> id for notice's lots."""
    if not lot_numbers:
        return {}
    lots = db.query(NoticeLot).filter(
        NoticeLot.notice_id == notice_id,
        NoticeLot.lot_number.in_(lot_numbers),
    ).all()
    return {str(l.lot_number): l.id for l in lots if l.lot_number is not None}


def get_document_by_id(db: Session, document_id: str) -> Optional[NoticeDocument]:
    """Get a notice document by id."""
    return db.query(NoticeDocument).filter(NoticeDocument.id == document_id).first()


def get_document_by_notice_and_id(
    db: Session, notice_id: str, document_id: str
) -> Optional[NoticeDocument]:
    """Get a notice document by notice_id and document_id (for API scope)."""
    return (
        db.query(NoticeDocument)
        .filter(
            NoticeDocument.notice_id == notice_id,
            NoticeDocument.id == document_id,
        )
        .first()
    )


def update_document_download_result(
    db: Session,
    document_id: str,
    local_path: Optional[str],
    content_type: Optional[str],
    file_size: Optional[int],
    sha256: Optional[str],
    download_status: str,
    download_error: Optional[str] = None,
) -> Optional[NoticeDocument]:
    """Update document after download. download_status: ok|failed. local_path None on failure."""
    doc = get_document_by_id(db, document_id)
    if not doc:
        return None
    doc.local_path = local_path
    doc.content_type = content_type
    doc.file_size = file_size
    doc.sha256 = sha256
    doc.downloaded_at = datetime.now(timezone.utc)
    doc.download_status = download_status
    doc.download_error = download_error
    db.commit()
    db.refresh(doc)
    return doc


def update_document_extraction_result(
    db: Session,
    document_id: str,
    extracted_text: Optional[str],
    extraction_status: str,
    extraction_error: Optional[str] = None,
) -> Optional[NoticeDocument]:
    """Update document after text extraction. extraction_status: ok|skipped|failed."""
    doc = get_document_by_id(db, document_id)
    if not doc:
        return None
    doc.extracted_text = extracted_text
    doc.extracted_at = datetime.now(timezone.utc)
    doc.extraction_status = extraction_status
    doc.extraction_error = extraction_error
    db.commit()
    db.refresh(doc)
    return doc
