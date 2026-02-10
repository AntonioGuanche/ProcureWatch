"""Authentication endpoints: register, login, me (real DB users)."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User

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


class UserOut(BaseModel):
    id: str
    email: str
    name: str


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
        user=UserOut(id=user.id, email=user.email, name=user.name),
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
        user=UserOut(id=user.id, email=user.email, name=user.name),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return current authenticated user."""
    return UserOut(id=current_user.id, email=current_user.email, name=current_user.name)
