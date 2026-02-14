"""CPV Intelligence API endpoints — sector-level market analytics."""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import rate_limit_public
from app.db.session import get_db
from app.services.cpv_intelligence import (
    get_full_cpv_analysis,
    list_cpv_groups_from_db,
    cpv_group_label,
    get_volume_value,
    get_top_winners,
    get_top_buyers,
    get_competition,
    get_active_opportunities,
)

router = APIRouter(
    prefix="/intelligence",
    tags=["intelligence"],
    dependencies=[Depends(rate_limit_public)],
)


@router.get("/cpv-groups")
def get_cpv_group_list(db: Session = Depends(get_db)) -> dict[str, Any]:
    """List ALL CPV groups (3-digit) found in the database, with counts and labels."""
    groups = list_cpv_groups_from_db(db)
    return {"groups": groups, "total": len(groups)}


@router.get("/cpv-analysis")
def cpv_analysis(
    cpv: str = Query(
        ...,
        description="Comma-separated 3-digit CPV group codes (e.g. '451,452')",
        min_length=3,
    ),
    months: int = Query(24, ge=6, le=120, description="Lookback period in months"),
    top_limit: int = Query(20, ge=5, le=50, description="Limit for top-N lists"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Full CPV intelligence analysis — all 11 sections.

    Returns volume/value trends, top winners, top buyers, competition level,
    procedure types, geography, seasonality, value distribution,
    single-bid contracts, award timeline, and active opportunities.

    Example: GET /api/intelligence/cpv-analysis?cpv=451,452&months=24
    """
    # Parse and validate CPV groups
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    if not cpv_groups:
        return {"error": "At least one CPV group code required"}
    if len(cpv_groups) > 10:
        return {"error": "Maximum 10 CPV groups at once"}
    # Validate: must be 3 digits
    for g in cpv_groups:
        if not (len(g) == 3 and g.isdigit()):
            return {"error": f"Invalid CPV group '{g}': must be exactly 3 digits"}

    return get_full_cpv_analysis(db, cpv_groups, months=months, top_limit=top_limit)


# --- Lightweight individual endpoints (for lazy-loading / caching) ---


@router.get("/cpv-volume")
def cpv_volume(
    cpv: str = Query(..., min_length=3),
    months: int = Query(24, ge=6, le=120),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Volume & value stats only (fast)."""
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    return get_volume_value(db, cpv_groups, months)


@router.get("/cpv-winners")
def cpv_winners(
    cpv: str = Query(..., min_length=3),
    limit: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Top award winners only."""
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    return {"winners": get_top_winners(db, cpv_groups, limit)}


@router.get("/cpv-buyers")
def cpv_buyers(
    cpv: str = Query(..., min_length=3),
    limit: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Top contracting authorities only."""
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    return {"buyers": get_top_buyers(db, cpv_groups, limit)}


@router.get("/cpv-competition")
def cpv_competition(
    cpv: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Competition level analysis only."""
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    return get_competition(db, cpv_groups)


@router.get("/cpv-opportunities")
def cpv_opportunities(
    cpv: str = Query(..., min_length=3),
    limit: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Active opportunities only (deadline in the future)."""
    cpv_groups = [g.strip() for g in cpv.split(",") if g.strip()]
    return get_active_opportunities(db, cpv_groups, limit)
