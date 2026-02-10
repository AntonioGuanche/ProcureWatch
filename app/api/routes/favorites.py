"""User favorites endpoints: add/remove/list bookmarked notices."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.api.schemas.notice import NoticeRead
from app.core.auth import rate_limit_public
from app.db.session import get_db
from app.models.notice import ProcurementNotice
from app.models.user import User
from app.models.user_favorite import UserFavorite

router = APIRouter(prefix="/favorites", tags=["favorites"], dependencies=[Depends(rate_limit_public)])


class FavoriteItem(BaseModel):
    notice: NoticeRead
    favorited_at: str


class FavoriteListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FavoriteItem]


class FavoriteIdsResponse(BaseModel):
    """Just the notice IDs that are favorited (for batch check)."""
    notice_ids: list[str]


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FavoriteListResponse:
    """List current user's favorited notices."""
    query = (
        db.query(UserFavorite, ProcurementNotice)
        .join(ProcurementNotice, UserFavorite.notice_id == ProcurementNotice.id)
        .filter(UserFavorite.user_id == current_user.id)
        .order_by(UserFavorite.created_at.desc())
    )
    total = query.count()
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()
    items = [
        FavoriteItem(
            notice=NoticeRead.model_validate(notice),
            favorited_at=fav.created_at.isoformat(),
        )
        for fav, notice in rows
    ]
    return FavoriteListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/ids", response_model=FavoriteIdsResponse)
async def list_favorite_ids(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FavoriteIdsResponse:
    """Get all favorited notice IDs for current user (for UI state)."""
    ids = (
        db.query(UserFavorite.notice_id)
        .filter(UserFavorite.user_id == current_user.id)
        .all()
    )
    return FavoriteIdsResponse(notice_ids=[r[0] for r in ids])


@router.post("/{notice_id}", status_code=201)
async def add_favorite(
    notice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Add a notice to favorites."""
    notice = db.query(ProcurementNotice).filter(ProcurementNotice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice non trouvée")
    existing = (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == current_user.id, UserFavorite.notice_id == notice_id)
        .first()
    )
    if existing:
        return {"status": "already_favorited"}
    fav = UserFavorite(user_id=current_user.id, notice_id=notice_id)
    db.add(fav)
    db.commit()
    return {"status": "favorited"}


@router.delete("/{notice_id}", status_code=200)
async def remove_favorite(
    notice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a notice from favorites."""
    fav = (
        db.query(UserFavorite)
        .filter(UserFavorite.user_id == current_user.id, UserFavorite.notice_id == notice_id)
        .first()
    )
    if not fav:
        raise HTTPException(status_code=404, detail="Favori non trouvé")
    db.delete(fav)
    db.commit()
    return {"status": "removed"}
