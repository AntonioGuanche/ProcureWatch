"""Dashboard KPI endpoints for frontend charts & cards."""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import rate_limit_public
from app.db.session import get_db
from app.services.dashboard_service import (
    get_import_health,
    get_overview,
    get_top_authorities,
    get_top_cpv,
    get_trends,
)

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(rate_limit_public)],
)


@router.get("/overview")
def dashboard_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Main KPI cards: totals, active, expiring, by source, value stats, freshness.

    Example response:
    {
        "total_notices": 10305,
        "active_notices": 1779,
        "expiring_7d": 42,
        "by_source": {"BOSA_EPROC": 10000, "TED_EU": 305},
        "added_24h": 0,
        "added_7d": 15,
        "value_stats": {"notices_with_value": 0, "min_eur": null, ...},
        ...
    }
    """
    return get_overview(db)


@router.get("/trends")
def dashboard_trends(
    days: int = Query(30, ge=7, le=365, description="Lookback period in days"),
    group_by: str = Query("day", pattern="^(day|week)$", description="Group by day or week"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Publication trends for line/bar charts.
    Returns per-source, per-date counts.

    Query params:
    - days: lookback window (default 30)
    - group_by: "day" or "week"
    """
    return get_trends(db, days=days, group_by=group_by)


@router.get("/top-cpv")
def dashboard_top_cpv(
    limit: int = Query(15, ge=5, le=50, description="Number of top CPV divisions"),
    active_only: bool = Query(False, description="Count only notices with future deadline"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Top CPV divisions by notice count, with human-readable labels.

    Example: {"data": [{"code": "45", "label": "Construction work", "count": 3227}, ...]}
    """
    return get_top_cpv(db, limit=limit, active_only=active_only)


@router.get("/top-authorities")
def dashboard_top_authorities(
    limit: int = Query(15, ge=5, le=50, description="Number of top authorities"),
    active_only: bool = Query(False, description="Count only notices with future deadline"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Top contracting authorities by notice count.
    Extracts name from multilingual organisation_names JSON.
    """
    return get_top_authorities(db, limit=limit, active_only=active_only)


@router.get("/health")
def dashboard_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Import pipeline health & data quality:
    - Last import per source
    - Data freshness (hours since last import)
    - Field fill rates (% of notices with each field populated)
    """
    return get_import_health(db)
