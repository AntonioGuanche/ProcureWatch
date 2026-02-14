"""TED CPV fix, TED CAN award enrichment."""
import logging
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_admin_key, rate_limit_admin
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["ted"],
    dependencies=[Depends(require_admin_key), Depends(rate_limit_admin)],
)

# ── TED CPV cleanup (fix ['xxxx'] format) ─────────────────────────────

@router.post(
    "/fix-ted-cpv",
    tags=["admin"],
    summary="Fix TED CPV codes stored as ['xxxx'] instead of clean codes",
    description=(
        "Strips brackets/quotes from cpv_main_code for TED notices.\n"
        "Also re-derives cpv_division (first 2 digits) for facet accuracy."
    ),
)
def fix_ted_cpv(
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Clean up TED CPV codes stored with list formatting."""
    import re

    # Find all notices with malformed CPV (contains [ or ')
    rows = db.execute(text(
        "SELECT id, cpv_main_code FROM notices "
        "WHERE cpv_main_code IS NOT NULL "
        "  AND (cpv_main_code LIKE '%[%' OR cpv_main_code LIKE '%]%' "
        "       OR cpv_main_code LIKE '%''%')"
    )).fetchall()

    if dry_run:
        samples = [{"id": str(r[0]), "before": r[1]} for r in rows[:20]]
        return {
            "total_malformed": len(rows),
            "dry_run": True,
            "samples": samples,
            "message": "Set dry_run=false to fix",
        }

    fixed = 0
    for row in rows:
        notice_id, raw_cpv = row[0], row[1]
        # Extract digits and dash from the messy string: "['44411000']" → "44411000"
        cleaned = re.sub(r"[\[\]\"' ]", "", raw_cpv).strip()
        # If multiple codes separated by comma, take the first
        if "," in cleaned:
            cleaned = cleaned.split(",")[0].strip()

        if cleaned and cleaned != raw_cpv:
            db.execute(text(
                "UPDATE notices SET cpv_main_code = :cpv WHERE id = :id"
            ), {"cpv": cleaned, "id": notice_id})
            fixed += 1

    db.commit()
    return {"total_malformed": len(rows), "fixed": fixed}


# ── TED CAN award enrichment (re-fetch expanded fields) ──────────────

@router.post(
    "/ted-can-enrich",
    tags=["admin"],
    summary="Re-enrich TED CANs that have country-code-only winner names",
    description=(
        "Finds TED notices where award_winner_name is just a country code (e.g. 'BEL', 'FR')\n"
        "and re-fetches from TED search with expanded fields (organisation-name-tenderer, etc.).\n"
        "Fixes the gap where DEFAULT_FIELDS didn't include winner detail fields."
    ),
)
def ted_can_enrich(
    limit: int = Query(500, ge=1, le=5000, description="Max notices to process"),
    batch_size: int = Query(10, ge=1, le=50, description="Notices per batch"),
    api_delay_ms: int = Query(500, ge=100, le=5000, description="Delay between API calls (ms)"),
    dry_run: bool = Query(True, description="Preview only — set false to execute"),
    db: Session = Depends(get_db),
) -> dict:
    """Re-enrich TED CANs with proper winner names."""
    from app.services.ted_award_enrichment import enrich_ted_can_batch
    return enrich_ted_can_batch(
        db,
        limit=limit,
        batch_size=batch_size,
        api_delay_ms=api_delay_ms,
        dry_run=dry_run,
    )


