"""Health check endpoints."""
from fastapi import APIRouter, HTTPException

from app.db.session import check_db_connection

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint with database connectivity check.
    Returns 503 if database is unreachable.
    """
    db_ok = check_db_connection()
    
    if db_ok:
        return {"status": "ok", "db": "ok"}
    else:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "db": "error"}
        )
