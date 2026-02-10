"""Admin-only endpoints: user stats, system overview."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.user_favorite import UserFavorite

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: require admin user."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user


@router.get("/stats")
async def admin_stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Global admin stats: user count, watchlist count, favorite count."""
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    total_watchlists = db.query(func.count(Watchlist.id)).scalar() or 0
    enabled_watchlists = db.query(func.count(Watchlist.id)).filter(Watchlist.enabled.is_(True)).scalar() or 0
    total_favorites = db.query(func.count(UserFavorite.id)).scalar() or 0

    return {
        "users": {
            "total": total_users,
            "active": active_users,
        },
        "watchlists": {
            "total": total_watchlists,
            "enabled": enabled_watchlists,
        },
        "favorites_total": total_favorites,
    }


@router.get("/users")
async def admin_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """List all users with basic info (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "is_admin": getattr(u, "is_admin", False),
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


# ── One-time bootstrap: promote user to admin via secret ──────────

@router.get("/bootstrap/{secret}")
async def bootstrap_admin(secret: str, db: Session = Depends(get_db)) -> dict:
    """One-time endpoint to set first admin. Remove after use."""
    import os
    expected = os.environ.get("ADMIN_BOOTSTRAP_SECRET", "pw-bootstrap-2026-admin")
    if secret != expected:
        raise HTTPException(status_code=403, detail="Invalid secret")
    user = db.query(User).filter(User.email == "antonio.ramirezguanche@gmail.com").first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = True
    db.commit()
    return {"status": "ok", "message": f"Admin activé pour {user.email}"}


# ── Backfill documents from raw_data ──────────────────────────────

@router.post("/backfill-documents")
async def backfill_documents(
    source: str | None = None,
    replace: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Extract documents from raw_data for all notices and persist as NoticeDocument rows."""
    from app.services.document_extraction import backfill_documents_for_all
    stats = backfill_documents_for_all(db, source=source, replace=replace)
    return {"status": "ok", **stats}


# ── Full historical import (background) ──────────────────────────

import threading
from datetime import datetime, timezone as tz

_full_import_status: dict = {"running": False}


@router.post("/full-import")
async def trigger_full_import(
    ted_start: str = "2025-01-01",
    run_bosa: bool = True,
    run_ted: bool = True,
    page_size: int = 200,
    _admin: User = Depends(require_admin),
) -> dict:
    """Launch full historical import in background thread. Returns immediately."""
    global _full_import_status

    if _full_import_status.get("running"):
        return {
            "status": "already_running",
            "started_at": _full_import_status.get("started_at"),
            "progress": _full_import_status.get("progress", ""),
        }

    _full_import_status = {
        "running": True,
        "started_at": datetime.now(tz.utc).isoformat(),
        "progress": "Starting...",
        "result": None,
    }

    def _run():
        global _full_import_status
        try:
            from scripts.full_import import run_full_import
            result = run_full_import(
                ted_start=ted_start,
                run_bosa=run_bosa,
                run_ted=run_ted,
                page_size=page_size,
            )
            _full_import_status["result"] = result
            _full_import_status["progress"] = (
                f"Done: +{result['totals']['created']} created, "
                f"{result['totals']['updated']} updated in {result['elapsed_seconds']}s"
            )
        except Exception as e:
            _full_import_status["result"] = {"error": str(e)}
            _full_import_status["progress"] = f"Error: {e}"
        finally:
            _full_import_status["running"] = False
            _full_import_status["completed_at"] = datetime.now(tz.utc).isoformat()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "status": "started",
        "ted_start": ted_start,
        "run_bosa": run_bosa,
        "run_ted": run_ted,
        "message": "Import lancé en arrière-plan. Vérifiez /api/admin/full-import/status",
    }


@router.get("/full-import/status")
async def full_import_status(
    _admin: User = Depends(require_admin),
) -> dict:
    """Check status of running full import."""
    return _full_import_status
