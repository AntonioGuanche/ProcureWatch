"""Health check endpoints."""
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.session import check_db_connection, SessionLocal

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check with database connectivity, notice count, and last import info.
    Returns 503 if database is unreachable.
    """
    db_ok = check_db_connection()

    if not db_ok:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "db": "error"},
        )

    info: dict[str, Any] = {"status": "ok", "db": "ok"}

    try:
        db = SessionLocal()
        try:
            # Notice count
            count = db.execute(text("SELECT COUNT(*) FROM notices")).scalar()
            info["notices"] = count or 0

            # Last import run
            row = db.execute(
                text(
                    "SELECT source, started_at, created_count, updated_count, error_count "
                    "FROM import_runs ORDER BY started_at DESC LIMIT 1"
                )
            ).mappings().first()
            if row:
                info["last_import"] = {
                    "source": row["source"],
                    "at": str(row["started_at"]),
                    "created": row["created_count"],
                    "updated": row["updated_count"],
                    "errors": row["error_count"],
                }
        finally:
            db.close()
    except Exception:
        # Don't fail health check if import_runs table doesn't exist yet
        pass

    return info
