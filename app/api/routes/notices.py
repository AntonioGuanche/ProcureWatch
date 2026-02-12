"""Notice endpoints."""
import asyncio
import time
import uuid
from collections import deque
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.auth import rate_limit_public
from app.api.routes.auth import get_optional_user

from app.api.schemas.notice import (
    NoticeDetailRead,
    NoticeDocumentListResponse,
    NoticeDocumentRead,
    NoticeDocumentTextRead,
    NoticeListResponse,
    NoticeLotListResponse,
    NoticeLotRead,
    NoticeRead,
    NoticeSearchItem,
    NoticeSearchResponse,
    NoticeStatsResponse,
    RefreshAcceptedResponse,
    RefreshJobStatusResponse,
    RefreshRequest,
    RefreshResponse,
)
from app.db.crud.notice_detail import (
    get_notice_detail_by_notice_id,
    get_document_by_notice_and_id,
    list_documents_by_notice_id,
    list_lots_by_notice_id,
)
from app.db.session import SessionLocal, get_db
from app.models.notice import NoticeSource, ProcurementNotice
from app.db.crud.notices import get_notice_by_id, get_notice_stats, list_notices
from app.services.notice_service import NoticeService

router = APIRouter(prefix="/notices", tags=["notices"])

# --- Rate limiting: 5 refresh requests per minute per client IP ---
_REFRESH_RATE_LIMIT_COUNT = 5
_REFRESH_RATE_LIMIT_WINDOW_SEC = 60
_refresh_timestamps: dict[str, deque[float]] = {}

# --- In-memory job store for async refresh (202) ---
_refresh_jobs: dict[str, dict[str, Any]] = {}


def _rate_limit_refresh(client_key: str) -> None:
    """Raise HTTP 429 if client has exceeded refresh rate limit."""
    now = time.time()
    if client_key not in _refresh_timestamps:
        _refresh_timestamps[client_key] = deque(maxlen=_REFRESH_RATE_LIMIT_COUNT)
    q = _refresh_timestamps[client_key]
    while q and q[0] < now - _REFRESH_RATE_LIMIT_WINDOW_SEC:
        q.popleft()
    if len(q) >= _REFRESH_RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=429,
            detail=f"Refresh rate limit exceeded: max {_REFRESH_RATE_LIMIT_COUNT} requests per {_REFRESH_RATE_LIMIT_WINDOW_SEC} seconds",
        )
    q.append(now)


def _run_refresh_sync(search_criteria: dict[str, Any], sources: Optional[list[str]], fetch_details: bool) -> dict[str, Any]:
    """Run import in a new DB session (for background task). Returns service result."""
    db = SessionLocal()
    try:
        service = NoticeService(db)
        return asyncio.run(service.import_from_all_sources(search_criteria, fetch_details=fetch_details, sources=sources))
    finally:
        db.close()


@router.get("/stats", response_model=NoticeStatsResponse)
async def get_notices_stats(db: Session = Depends(get_db)) -> NoticeStatsResponse:
    """Return aggregate notice counts by source and last import time."""
    data = get_notice_stats(db)
    return NoticeStatsResponse(
        total_notices=data["total_notices"],
        by_source=data["by_source"],
        last_import=data["last_import"],
    )


def _build_search_criteria(body: RefreshRequest) -> tuple[dict[str, Any], Optional[list[str]]]:
    criteria = body.search_criteria
    search_criteria: dict[str, Any] = {
        "keywords": criteria.keywords if criteria else None,
        "term": (criteria.keywords if criteria else None) or "",
        "page": criteria.page if criteria else 1,
        "page_size": criteria.page_size if criteria else 25,
    }
    if criteria and criteria.cpv_codes:
        search_criteria["cpv"] = criteria.cpv_codes[0]
    if criteria and criteria.publication_date_from:
        search_criteria["publication_date_from"] = criteria.publication_date_from
    if criteria and criteria.publication_date_to:
        search_criteria["publication_date_to"] = criteria.publication_date_to
    return search_criteria, body.sources


@router.post("/refresh")
async def post_notices_refresh(
    body: RefreshRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    async_mode: bool = Query(False, alias="async", description="If true, return 202 + job_id and run in background"),
):
    """
    Run notice refresh (BOSA + TED). Uses NoticeService.import_from_all_sources().
    Rate limited: 5 requests per minute per client IP.
    - Default: run synchronously, return 200 with stats and duration_seconds.
    - ?async=1: return 202 Accepted with job_id; poll GET /api/notices/refresh/jobs/{job_id} for result.
    """
    client_key = request.client.host if request.client else "default"
    _rate_limit_refresh(client_key)

    search_criteria, sources = _build_search_criteria(body)

    if async_mode:
        job_id = str(uuid.uuid4())
        _refresh_jobs[job_id] = {
            "status": "pending",
            "result": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        def _task() -> None:
            _refresh_jobs[job_id]["status"] = "running"
            start = time.perf_counter()
            try:
                res = _run_refresh_sync(search_criteria, sources, fetch_details=True)
                duration = time.perf_counter() - start
                _refresh_jobs[job_id]["status"] = "completed"
                _refresh_jobs[job_id]["result"] = {
                    "status": "success",
                    "stats": {
                        "bosa": res["bosa"],
                        "ted": res["ted"],
                        "total_created": res["total"]["created"],
                        "total_updated": res["total"]["updated"],
                    },
                    "duration_seconds": round(duration, 2),
                }
            except Exception as e:
                _refresh_jobs[job_id]["status"] = "failed"
                _refresh_jobs[job_id]["result"] = {
                    "status": "failed",
                    "stats": {
                        "bosa": {"created": 0, "updated": 0, "skipped": 0, "errors": [{"message": str(e)}]},
                        "ted": {"created": 0, "updated": 0, "skipped": 0, "errors": []},
                        "total_created": 0,
                        "total_updated": 0,
                    },
                    "duration_seconds": 0,
                }

        background_tasks.add_task(_task)
        return RefreshAcceptedResponse(
            status="accepted",
            job_id=job_id,
            message="Refresh started in background. Poll GET /api/notices/refresh/jobs/{job_id} for result.",
        )

    service = NoticeService(db)
    start = time.perf_counter()
    result = await service.import_from_all_sources(search_criteria, fetch_details=True, sources=sources)
    duration = time.perf_counter() - start
    return RefreshResponse(
        status="success",
        stats={
            "bosa": result["bosa"],
            "ted": result["ted"],
            "total_created": result["total"]["created"],
            "total_updated": result["total"]["updated"],
        },
        duration_seconds=round(duration, 2),
    )


@router.get("/refresh/jobs/{job_id}", response_model=RefreshJobStatusResponse)
async def get_notices_refresh_job(job_id: str) -> RefreshJobStatusResponse:
    """Get status and result of an async refresh job."""
    if job_id not in _refresh_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _refresh_jobs[job_id]
    result = None
    if job.get("result"):
        r = job["result"]
        result = RefreshResponse(
            status=r.get("status", "success"),
            stats=r.get("stats", {}),
            duration_seconds=r.get("duration_seconds", 0),
        )
    return RefreshJobStatusResponse(
        job_id=job_id,
        status=job.get("status", "pending"),
        result=result,
        created_at=job.get("created_at"),
    )


@router.get("", response_model=NoticeListResponse)
async def get_notices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    term: Optional[str] = Query(None, alias="q", description="Search term in title"),
    sources: Optional[list[str]] = Query(None, description="Filter by sources (e.g. TED, BOSA); comma-separated or repeated ?sources=TED&sources=BOSA; omit for all"),
    cpv: Optional[str] = Query(None, description="Filter by CPV code (main or additional)"),
    buyer: Optional[str] = Query(None, description="Filter by buyer name"),
    deadline_from: Optional[datetime] = Query(None, description="Filter by deadline from (ISO datetime)"),
    deadline_to: Optional[datetime] = Query(None, description="Filter by deadline to (ISO datetime)"),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    """List notices with pagination and optional filtering."""
    offset = (page - 1) * page_size
    # Parse sources: list from repeated params or comma-separated; None/empty = return all
    sources_list: Optional[list[str]] = None
    if sources:
        sources_list = [s.strip() for part in sources for s in str(part).split(",") if s.strip()]
        if not sources_list:
            sources_list = None

    notices, total = list_notices(
        db,
        limit=page_size,
        offset=offset,
        q=term,
        cpv=cpv,
        buyer=buyer,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        sources=sources_list,
    )
    
    return NoticeListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=notices,
    )


@router.get("/search", response_model=NoticeSearchResponse, dependencies=[Depends(rate_limit_public)])
def search_notices(
    q: Optional[str] = Query(None, description="Full-text keyword search (title + description). Supports AND/OR."),
    cpv: Optional[str] = Query(None, description="CPV code prefix filter (e.g. '45' or '45000000')"),
    nuts: Optional[str] = Query(None, description="NUTS code prefix filter (e.g. 'BE1' or 'BE100')"),
    source: Optional[str] = Query(None, description="Source filter: BOSA, TED, or comma-separated 'BOSA,TED'"),
    authority: Optional[str] = Query(None, description="Authority / organisation name search"),
    notice_type: Optional[str] = Query(None, description="Notice type filter (e.g. 'CONTRACT_NOTICE')"),
    date_from: Optional[str] = Query(None, description="Publication date from (ISO YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Publication date to (ISO YYYY-MM-DD)"),
    deadline_before: Optional[str] = Query(None, description="Deadline before (ISO YYYY-MM-DD)"),
    deadline_after: Optional[str] = Query(None, description="Deadline after (ISO YYYY-MM-DD) — use for 'still open'"),
    value_min: Optional[float] = Query(None, ge=0, description="Minimum estimated value (EUR)"),
    value_max: Optional[float] = Query(None, ge=0, description="Maximum estimated value (EUR)"),
    active_only: bool = Query(False, description="If true, only notices with deadline in the future"),
    sort: str = Query("date_desc", description="Sort: date_desc, date_asc, relevance, deadline, deadline_desc, value_desc, value_asc, award_desc, award_asc, award_date_desc, award_date_asc, cpv_asc, cpv_desc, source_asc, source_desc"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> NoticeSearchResponse:
    """
    Advanced search with full-text (PostgreSQL tsvector) + filters.
    Public, no auth. All filters optional; returns paginated items with total count.

    Filters:
    - q: keywords (AND by default, OR explicit)
    - cpv: CPV prefix (e.g. "45" for construction)
    - nuts: NUTS prefix (e.g. "BE1" for Brussels region)
    - source: BOSA, TED, or comma-separated
    - authority: organisation name (ILIKE)
    - notice_type: exact match
    - date_from / date_to: publication date range
    - deadline_before / deadline_after: deadline range
    - value_min / value_max: estimated value range (EUR)
    - active_only: only notices with deadline > now

    Sort options: date_desc (default), date_asc, relevance (auto when q),
                  deadline, deadline_desc, value_desc, value_asc
    """
    from app.services.search_service import build_search_query

    # Parse date strings
    d_from = _safe_date(date_from)
    d_to = _safe_date(date_to)
    d_deadline_before = _safe_date(deadline_before)
    d_deadline_after = _safe_date(deadline_after)

    # Parse multi-source: "BOSA,TED" → ["BOSA", "TED"]
    sources_list: Optional[list[str]] = None
    if source and source.strip():
        sources_list = [s.strip() for s in source.split(",") if s.strip()]
        if len(sources_list) == 1:
            sources_list = None  # single source handled as before

    # If keyword search and no explicit sort, default to relevance
    effective_sort = sort
    if q and q.strip() and sort == "date_desc":
        effective_sort = "relevance"

    query, _has_rank = build_search_query(
        db,
        q=q,
        cpv=cpv,
        nuts=nuts,
        source=source.split(",")[0].strip() if source and "," not in source else None,
        sources=sources_list,
        authority=authority,
        notice_type=notice_type,
        date_from=d_from,
        date_to=d_to,
        deadline_before=d_deadline_before,
        deadline_after=d_deadline_after,
        value_min=value_min,
        value_max=value_max,
        active_only=active_only,
        sort=effective_sort,
    )

    # Count + paginate
    total = query.count()
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    items = [
        NoticeSearchItem(
            id=n.id,
            title=n.title,
            source=n.source,
            cpv_main_code=n.cpv_main_code,
            nuts_codes=n.nuts_codes,
            organisation_names=n.organisation_names,
            publication_date=n.publication_date.isoformat() if n.publication_date else None,
            deadline=n.deadline.isoformat() if n.deadline else None,
            reference_number=n.reference_number,
            description=(n.description[:300] if n.description else None),
            notice_type=n.notice_type,
            form_type=n.form_type,
            estimated_value=float(n.estimated_value) if n.estimated_value else None,
            url=n.url,
            status=n.status,
            award_winner_name=n.award_winner_name,
            award_value=float(n.award_value) if n.award_value else None,
            award_date=n.award_date.isoformat() if n.award_date else None,
            number_tenders_received=n.number_tenders_received,
        )
        for n in rows
    ]
    total_pages = (total + page_size - 1) // page_size if page_size else 0

    return NoticeSearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/facets", dependencies=[Depends(rate_limit_public)])
def get_notice_facets(db: Session = Depends(get_db)) -> dict:
    """
    Dynamic filter values for UI dropdowns/facets:
    sources, top CPV divisions, notice types, date range.
    """
    from app.services.search_service import get_facets
    return get_facets(db)


def _safe_date(val: Optional[str]) -> Optional[date]:
    """Parse ISO date string, return None on failure."""
    if not val:
        return None
    try:
        return date.fromisoformat(val.strip())
    except (ValueError, AttributeError):
        return None


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


# --- AI Summary ---

@router.post("/{notice_id}/summary")
async def generate_notice_summary(
    notice_id: str,
    lang: str = Query("fr", regex="^(fr|nl|en|de)$", description="Target language"),
    force: bool = Query(False, description="Force regeneration even if cached"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """Generate AI summary for a notice.

    Requires authentication. Plan-gated: Pro gets 20/month, Business unlimited, Free none.
    Returns cached summary if available (unless force=True).
    """
    from app.services.ai_summary import generate_summary, check_ai_usage, increment_ai_usage

    notice = get_notice_by_id(db, notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    # Return cached if available and no force
    if not force and notice.ai_summary and notice.ai_summary_lang == lang:
        return {
            "notice_id": notice_id,
            "summary": notice.ai_summary,
            "lang": notice.ai_summary_lang,
            "generated_at": notice.ai_summary_generated_at.isoformat() if notice.ai_summary_generated_at else None,
            "cached": True,
        }

    # Auth required for generation
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise pour les résumés IA")

    # Check plan limits
    usage_error = check_ai_usage(db, current_user)
    if usage_error:
        raise HTTPException(status_code=403, detail=usage_error)

    # Generate
    summary = await generate_summary(db, notice, lang=lang, force=force)
    if not summary:
        raise HTTPException(status_code=503, detail="Impossible de générer le résumé IA. Réessayez plus tard.")

    # Increment usage
    increment_ai_usage(db, current_user)

    return {
        "notice_id": notice_id,
        "summary": summary,
        "lang": lang,
        "generated_at": notice.ai_summary_generated_at.isoformat() if notice.ai_summary_generated_at else None,
        "cached": False,
    }
