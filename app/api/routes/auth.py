"""Authentication endpoints: register, login, me, forgot/reset password."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_reset_token,
    decode_access_token,
    decode_reset_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.notifications.emailer import send_email_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# --- Schemas ---


class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetPasswordBody(BaseModel):
    token: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool = False
    plan: str = "free"


class LoginResponse(BaseModel):
    access_token: str
    user: UserOut


# --- Dependency: get current user from JWT ---


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Validate Bearer token and return User ORM object. Raises 401 if invalid."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token invalide")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


# --- Endpoints ---


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(body: RegisterBody, db: Session = Depends(get_db)) -> LoginResponse:
    """Create a new user account."""
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")

    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Le mot de passe doit contenir au moins 8 caractères")

    name = (body.name or body.email.split("@")[0]).strip()
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        name=name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"New user registered: {user.email} (id={user.id})")
    token = create_access_token(sub=user.email, user_id=user.id, name=user.name)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user.id, email=user.email, name=user.name, is_admin=getattr(user, 'is_admin', False), plan=getattr(user, 'plan', 'free')),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody, db: Session = Depends(get_db)) -> LoginResponse:
    """Login with email + password, get JWT."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(sub=user.email, user_id=user.id, name=user.name)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user.id, email=user.email, name=user.name, is_admin=getattr(user, 'is_admin', False), plan=getattr(user, 'plan', 'free')),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return current authenticated user."""
    return UserOut(id=current_user.id, email=current_user.email, name=current_user.name, is_admin=getattr(current_user, 'is_admin', False), plan=getattr(current_user, 'plan', 'free'))


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordBody, db: Session = Depends(get_db)) -> dict:
    """Send password reset email. Always returns 200 (no email enumeration)."""
    user = db.query(User).filter(User.email == body.email.lower()).first()

    if user and user.is_active:
        token = create_reset_token(user_id=user.id, email=user.email)
        reset_url = f"{settings.app_url}/reset-password?token={token}"

        html = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #1e293b;">ProcureWatch</h2>
            <p>Bonjour {user.name},</p>
            <p>Vous avez demandé la réinitialisation de votre mot de passe.</p>
            <p style="margin: 24px 0;">
                <a href="{reset_url}"
                   style="background: #2563eb; color: white; padding: 12px 24px;
                          border-radius: 6px; text-decoration: none; font-weight: 500;">
                    Réinitialiser mon mot de passe
                </a>
            </p>
            <p style="color: #6b7280; font-size: 14px;">
                Ce lien est valable 1 heure. Si vous n'êtes pas à l'origine de cette demande,
                ignorez cet email.
            </p>
        </div>
        """
        try:
            send_email_html(
                to=user.email,
                subject="ProcureWatch — Réinitialisation du mot de passe",
                html_body=html,
            )
            logger.info(f"Password reset email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send reset email to {user.email}: {e}")

    # Always return success (prevent email enumeration)
    return {"message": "Si un compte existe avec cet email, un lien de réinitialisation a été envoyé."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)) -> dict:
    """Reset password using a valid reset token."""
    payload = decode_reset_token(body.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")

    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")

    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Le mot de passe doit contenir au moins 8 caractères")

    user.password_hash = hash_password(body.password)
    db.commit()
    logger.info(f"Password reset for {user.email}")

    return {"message": "Mot de passe modifié avec succès. Vous pouvez vous connecter."}


# --- Profile Management ---


class UpdateProfileBody(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.put("/profile", response_model=UserOut)
async def update_profile(
    body: UpdateProfileBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update current user's profile (name, email)."""
    if body.name is not None:
        current_user.name = body.name.strip()
    if body.email is not None:
        new_email = body.email.lower()
        if new_email != current_user.email:
            existing = db.query(User).filter(User.email == new_email).first()
            if existing:
                raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
            current_user.email = new_email
    db.commit()
    db.refresh(current_user)
    return UserOut(id=current_user.id, email=current_user.email, name=current_user.name, is_admin=getattr(current_user, 'is_admin', False), plan=getattr(current_user, 'plan', 'free'))


@router.put("/password")
async def change_password(
    body: ChangePasswordBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Change password (requires current password)."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit contenir au moins 8 caractères")
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "ok", "message": "Mot de passe modifié"}


@router.delete("/account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Permanently delete current user account and all associated data."""
    from app.models.watchlist import Watchlist, WatchlistMatch
    from app.models.user_favorite import UserFavorite

    # Delete user's watchlist matches, watchlists, favorites
    wl_ids = [w.id for w in db.query(Watchlist.id).filter(Watchlist.user_id == current_user.id).all()]
    if wl_ids:
        db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id.in_(wl_ids)).delete(synchronize_session=False)
    db.query(Watchlist).filter(Watchlist.user_id == current_user.id).delete(synchronize_session=False)
    db.query(UserFavorite).filter(UserFavorite.user_id == current_user.id).delete(synchronize_session=False)
    db.delete(current_user)
    db.commit()
    logger.info(f"User account deleted: {current_user.email} (id={current_user.id})")
    return {"status": "ok", "message": "Compte supprimé"}
