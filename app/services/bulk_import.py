"""Bulk import service: auto-paginating import with progress tracking.

Fetches all available notices from BOSA and/or TED by auto-paginating
through all pages. Commits in batches to avoid huge transactions.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.notice_service import NoticeService

logger = logging.getLogger(__name__)


def _ted_term_with_date(base_term: str, days_back: int = 3) -> str:
    """Build TED expert query with rolling publication date filter.
    
    If base_term already contains PD filter, return as-is.
    Otherwise append AND PD >= <date> to restrict to recent notices.
    Wraps compound terms (containing OR) in parentheses for correct precedence.
    """
    from datetime import date, timedelta
    if "PD " in base_term or "PD>" in base_term or "publication-date" in base_term:
        return base_term
    cutoff = (date.today() - timedelta(days=days_back)).strftime("%Y%m%d")
    if base_term.strip() in ("*", ""):
        return f"PD >= {cutoff}"
    # Wrap in parens if compound (OR) to ensure correct precedence with AND
    if " OR " in base_term:
        return f"({base_term}) AND PD >= {cutoff}"
    return f"{base_term} AND PD >= {cutoff}"


# Hard safety limit to prevent runaway imports
MAX_TOTAL_PAGES = 100
MAX_PAGE_SIZE = 250


def _fetch_page_bosa(term: str, page: int, page_size: int) -> dict[str, Any]:
    """Fetch one page from BOSA. Returns {items: [...], total_count: int|None}."""
    from app.connectors.bosa.client import search_publications
    result = search_publications(term=term, page=page, page_size=page_size)

    metadata = result.get("metadata") or {}
    total_count = metadata.get("totalCount")

    payload = result.get("json") or {}
    if isinstance(payload, dict):
        # Also check totalCount in payload
        if total_count is None:
            total_count = payload.get("totalCount")
        for key in ("publications", "items", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return {"items": candidate, "total_count": total_count}

    return {"items": [], "total_count": total_count}


def _fetch_page_ted(term: str, page: int, page_size: int) -> dict[str, Any]:
    """Fetch one page from TED. Returns {items: [...], total_count: int|None}."""
    from app.connectors.ted.client import search_ted_notices
    result = search_ted_notices(term=term, page=page, page_size=page_size)

    metadata = result.get("metadata") or {}
    total_count = metadata.get("totalCount")

    payload = result.get("json") or {}
    if isinstance(payload, dict):
        if total_count is None:
            total_count = payload.get("totalCount") or payload.get("total")
        notices = payload.get("notices") or payload.get("items") or []
        return {"items": notices, "total_count": total_count}

    return {"items": [], "total_count": total_count}


def bulk_import_source(
    db: Session,
    source: str,
    term: str = "*",
    page_size: int = 100,
    max_pages: Optional[int] = None,
    fetch_details: bool = False,
) -> dict[str, Any]:
    """
    Auto-paginating import for a single source.

    Args:
        source: "BOSA" or "TED"
        term: Search term
        page_size: Results per page (max 250)
        max_pages: Hard limit on pages (None = auto from totalCount, capped at MAX_TOTAL_PAGES)
        fetch_details: Fetch full workspace details (BOSA only, slower)

    Returns:
        Detailed stats with per-page breakdown.
    """
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    source = source.upper()

    if source not in ("BOSA", "TED"):
        return {"error": f"Unknown source: {source}"}

    fetch_fn = _fetch_page_bosa if source == "BOSA" else _fetch_page_ted
    svc = NoticeService(db)

    stats = {
        "source": source,
        "term": term,
        "page_size": page_size,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_created": 0,
        "total_updated": 0,
        "total_skipped": 0,
        "total_errors": 0,
        "pages_fetched": 0,
        "api_total_count": None,
        "pages": [],
    }

    page = 1
    effective_max = min(max_pages or MAX_TOTAL_PAGES, MAX_TOTAL_PAGES)

    while page <= effective_max:
        page_start = datetime.now(timezone.utc)

        try:
            result = fetch_fn(term, page, page_size)
            items = result.get("items", [])
            total_count = result.get("total_count")

            # Store total count from first page
            if page == 1 and total_count is not None:
                stats["api_total_count"] = total_count
                if max_pages is None and total_count is not None:
                    try:
                        needed_pages = (int(total_count) + page_size - 1) // page_size
                        effective_max = min(needed_pages, MAX_TOTAL_PAGES)
                    except (ValueError, TypeError):
                        pass

            if not items:
                logger.info("[Bulk %s] Page %d: empty, stopping", source, page)
                break

            # Import this page
            if source == "BOSA":
                page_stats = asyncio.run(
                    svc.import_from_eproc_search(items, fetch_details=fetch_details)
                )
            else:
                page_stats = asyncio.run(
                    svc.import_from_ted_search(items, fetch_details=fetch_details)
                )

            created = page_stats.get("created", 0)
            updated = page_stats.get("updated", 0)
            skipped = page_stats.get("skipped", 0)
            errors = page_stats.get("errors", [])

            stats["total_created"] += created
            stats["total_updated"] += updated
            stats["total_skipped"] += skipped
            stats["total_errors"] += len(errors)
            stats["pages_fetched"] += 1

            elapsed = (datetime.now(timezone.utc) - page_start).total_seconds()

            page_info = {
                "page": page,
                "items_received": len(items),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "errors": len(errors),
                "elapsed_seconds": round(elapsed, 1),
            }
            if errors:
                page_info["error_details"] = errors[:3]  # Cap error details
            stats["pages"].append(page_info)

            logger.info(
                "[Bulk %s] Page %d: %d items → %d new, %d updated (%.1fs)",
                source, page, len(items), created, updated, elapsed,
            )

            # If we got fewer items than page_size, we've reached the end
            if len(items) < page_size:
                logger.info("[Bulk %s] Last page (got %d < %d)", source, len(items), page_size)
                break

        except Exception as e:
            stats["total_errors"] += 1
            stats["pages"].append({
                "page": page,
                "error": str(e),
            })
            logger.exception("[Bulk %s] Page %d failed", source, page)
            # Continue to next page on error
            if page >= 3 and stats["total_created"] == 0 and stats["total_updated"] == 0:
                logger.warning("[Bulk %s] 3 pages with no results, aborting", source)
                break

        page += 1

    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    elapsed_total = (
        datetime.fromisoformat(stats["completed_at"])
        - datetime.fromisoformat(stats["started_at"])
    ).total_seconds()
    stats["elapsed_seconds"] = round(elapsed_total, 1)
    stats["effective_max_pages"] = effective_max

    return stats


def bulk_import_all(
    db: Session,
    sources: str = "BOSA,TED",
    term: str = "*",
    term_ted: Optional[str] = None,
    ted_days_back: int = 3,
    page_size: int = 100,
    max_pages: Optional[int] = None,
    fetch_details: bool = False,
    run_backfill: bool = True,
    run_matcher: bool = True,
) -> dict[str, Any]:
    """
    Full bulk import pipeline: import all sources → backfill → matcher.

    Args:
        term: Search term for BOSA (default: *)
        term_ted: Search term for TED (default: notice-type = cn*).
                  Automatically gets a rolling PD date filter appended.
        ted_days_back: Rolling date window for TED (default: 3 days)

    Returns comprehensive stats.
    """
    started_at = datetime.now(timezone.utc)
    source_list = [s.strip().upper() for s in sources.split(",") if s.strip()]

    results: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "sources": {},
    }

    total_created = 0
    total_updated = 0

    for source in source_list:
        if source == "TED" and term_ted:
            effective_term = _ted_term_with_date(term_ted, days_back=ted_days_back)
        elif source == "TED":
            effective_term = _ted_term_with_date(term, days_back=ted_days_back)
        else:
            effective_term = term
        logger.info("[Bulk %s] Using term: %s", source, effective_term)
        source_result = bulk_import_source(
            db, source=source, term=effective_term, page_size=page_size,
            max_pages=max_pages, fetch_details=fetch_details,
        )
        results["sources"][source.lower()] = source_result
        total_created += source_result.get("total_created", 0)
        total_updated += source_result.get("total_updated", 0)

    results["total_created"] = total_created
    results["total_updated"] = total_updated

    # Backfill enrichment
    if run_backfill and (total_created > 0 or total_updated > 0):
        try:
            from app.services.enrichment_service import backfill_from_raw_data, refresh_search_vectors
            bf = backfill_from_raw_data(db)
            results["backfill"] = bf
            if bf.get("enriched", 0) > 0:
                rows = refresh_search_vectors(db)
                results["search_vectors_refreshed"] = rows
        except Exception as e:
            results["backfill_error"] = str(e)
            logger.exception("[Bulk] Backfill failed")

    # Watchlist matcher
    if run_matcher and total_created > 0:
        try:
            from app.services.watchlist_matcher import run_watchlist_matcher
            results["watchlist_matcher"] = run_watchlist_matcher(db)
        except Exception as e:
            results["watchlist_matcher_error"] = str(e)
            logger.exception("[Bulk] Matcher failed")

    completed_at = datetime.now(timezone.utc)
    results["completed_at"] = completed_at.isoformat()
    results["elapsed_seconds"] = round((completed_at - started_at).total_seconds(), 1)

    logger.info(
        "[Bulk] Done: created=%d updated=%d elapsed=%.1fs",
        total_created, total_updated, results["elapsed_seconds"],
    )

    return results
