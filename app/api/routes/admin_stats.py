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
