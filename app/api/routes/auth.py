"""Authentication endpoints: register, login, me, forgot/reset password, profile."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator
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
from app.utils.vat import validate_vat

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


class CompanyProfileOut(BaseModel):
    """Company profile subset — returned in UserOut."""
    company_name: Optional[str] = None
    vat_number: Optional[str] = None
    nace_codes: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool = False
    plan: str = "free"
    # Company profile
    company_name: Optional[str] = None
    vat_number: Optional[str] = None
    nace_codes: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LoginResponse(BaseModel):
    access_token: str
    user: UserOut


def _user_out(user: User) -> UserOut:
    """Build UserOut from a User ORM instance — single source of truth."""
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        is_admin=getattr(user, "is_admin", False),
        plan=getattr(user, "plan", "free"),
        company_name=user.company_name,
        vat_number=user.vat_number,
        nace_codes=user.nace_codes,
        address=user.address,
        postal_code=user.postal_code,
        city=user.city,
        country=user.country,
        latitude=user.latitude,
        longitude=user.longitude,
    )


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


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of 401 if unauthenticated."""
    if not credentials or credentials.scheme != "Bearer":
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()


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
    return LoginResponse(access_token=token, user=_user_out(user))


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody, db: Session = Depends(get_db)) -> LoginResponse:
    """Login with email + password, get JWT."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(sub=user.email, user_id=user.id, name=user.name)
    return LoginResponse(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return current authenticated user."""
    return _user_out(current_user)


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
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit contenir au moins 8 caractères")

    user.password_hash = hash_password(body.password)
    db.commit()
    logger.info(f"Password reset for {user.email}")

    return {"message": "Mot de passe modifié avec succès. Vous pouvez vous connecter."}


# --- Profile Management ---


class UpdateProfileBody(BaseModel):
    """Update personal info + company profile. All fields optional (PATCH semantics)."""
    name: str | None = None
    email: EmailStr | None = None
    # Company
    company_name: str | None = None
    vat_number: str | None = None
    # Location
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().upper()
            if len(v) != 2 or not v.isalpha():
                raise ValueError("Code pays ISO 3166-1 alpha-2 attendu (ex: BE, FR, NL)")
        return v


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.put("/profile", response_model=UserOut)
async def update_profile(
    body: UpdateProfileBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update current user's profile (name, email, company info, address)."""
    # Personal info
    if body.name is not None:
        current_user.name = body.name.strip()
    if body.email is not None:
        new_email = body.email.lower()
        if new_email != current_user.email:
            existing = db.query(User).filter(User.email == new_email).first()
            if existing:
                raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
            current_user.email = new_email

    # VAT validation + normalization
    if body.vat_number is not None:
        is_valid, normalized, error = validate_vat(body.vat_number)
        if not is_valid:
            raise HTTPException(status_code=422, detail=error)
        if normalized:
            # Check uniqueness (another user might have the same VAT)
            existing = db.query(User).filter(
                User.vat_number == normalized,
                User.id != current_user.id,
            ).first()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="Ce numéro de TVA est déjà associé à un autre compte",
                )
        current_user.vat_number = normalized  # None if cleared

    # Company
    if body.company_name is not None:
        current_user.company_name = body.company_name.strip() or None

    # Location
    if body.address is not None:
        current_user.address = body.address.strip() or None
    if body.postal_code is not None:
        current_user.postal_code = body.postal_code.strip() or None
    if body.city is not None:
        current_user.city = body.city.strip() or None
    if body.country is not None:
        current_user.country = body.country

    # Geocode if address changed and we have enough info
    if any(getattr(body, f) is not None for f in ("address", "postal_code", "city", "country")):
        lat, lng = _geocode_user(current_user)
        if lat is not None:
            current_user.latitude = lat
            current_user.longitude = lng

    db.commit()
    db.refresh(current_user)
    return _user_out(current_user)


def _geocode_user(user: User) -> tuple[float | None, float | None]:
    """Best-effort geocoding from postal_code + city + country.

    Uses a simple Belgian postal code lookup table for the most common case.
    Falls back to None (no external API needed for MVP).
    """
    # Belgian postal code → approximate lat/lng (major cities + regions)
    # Full table not needed: postal_code[:2] gives the province
    _BE_POSTAL_PREFIXES: dict[str, tuple[float, float]] = {
        "10": (50.8503, 4.3517),    # Bruxelles
        "11": (50.8503, 4.3517),    # Bruxelles
        "12": (50.8503, 4.3517),    # Bruxelles / BW
        "13": (50.8800, 4.7000),    # Brabant wallon
        "14": (51.0500, 4.4800),    # Mechelen / Antwerpen
        "15": (51.0259, 4.4777),    # Mechelen
        "16": (50.8798, 4.7005),    # Brabant wallon
        "17": (50.7200, 4.4000),    # Nivelles
        "18": (50.7100, 4.6200),    # Wavre
        "19": (50.6700, 4.6100),    # Brabant wallon
        "20": (51.2194, 4.4025),    # Antwerpen
        "21": (51.2194, 4.4025),    # Antwerpen
        "22": (51.1200, 4.3400),    # Antwerpen
        "23": (51.1667, 4.4500),    # Antwerpen
        "24": (51.1300, 4.5700),    # Lier
        "25": (51.2600, 4.7700),    # Turnhout
        "26": (51.3400, 4.8600),    # Turnhout
        "29": (51.1600, 4.2900),    # Antwerpen
        "30": (50.8798, 4.7005),    # Leuven
        "31": (50.8798, 4.7005),    # Leuven
        "32": (50.9300, 4.8700),    # Tienen
        "33": (50.8300, 4.8800),    # Tienen
        "34": (50.9800, 4.7200),    # Aarschot
        "35": (50.9500, 5.0000),    # Hageland
        "36": (50.8900, 4.5600),    # Leuven peripherie
        "37": (50.8800, 4.7000),    # Leuven sud
        "38": (50.8500, 3.2500),    # Ieper
        "39": (50.8300, 3.0300),    # Poperinge
        "40": (51.0543, 3.7174),    # Gent
        "41": (51.0500, 4.0000),    # Dendermonde
        "42": (51.0400, 4.0200),    # Sint-Niklaas
        "43": (50.9300, 3.6400),    # Oudenaarde
        "44": (51.0300, 3.4200),    # Eeklo
        "45": (50.9400, 3.8800),    # Aalst
        "46": (51.0900, 3.8500),    # Lokeren
        "47": (51.0000, 4.1800),    # Hamme
        "48": (51.1400, 3.6200),    # Evergem
        "49": (51.1000, 3.4700),    # Maldegem
        "50": (50.6292, 5.5797),    # Liège
        "51": (50.5900, 5.8000),    # Verviers
        "52": (50.4900, 5.8500),    # Spa
        "53": (50.6400, 5.5600),    # Liège
        "54": (50.6100, 5.4800),    # Seraing
        "55": (50.6600, 5.7400),    # Herve
        "56": (50.4541, 3.9523),    # Tournai / Hainaut
        "57": (50.4500, 3.5600),    # Mouscron
        "58": (50.5200, 3.7400),    # Ath
        "59": (50.4600, 3.8600),    # Hainaut
        "60": (50.4108, 4.4446),    # Charleroi
        "61": (50.2100, 5.5700),    # Marche-en-Famenne
        "62": (50.4700, 4.8700),    # Namur
        "63": (50.6100, 5.9600),    # Eupen
        "64": (50.4500, 4.4200),    # Charleroi
        "65": (50.4500, 3.8400),    # Mons
        "66": (50.3700, 3.9800),    # Mons
        "67": (50.3600, 3.5700),    # Mons / Dour
        "68": (50.7700, 3.8700),    # Ath
        "69": (50.2800, 4.0800),    # Hainaut sud
        "70": (50.4541, 3.9523),    # Mons / Centre
        "71": (50.9800, 5.4100),    # Hasselt
        "72": (50.9900, 5.3800),    # Hasselt
        "73": (50.8900, 5.6700),    # Tongeren
        "74": (51.0500, 5.5800),    # Genk
        "75": (50.7200, 5.5800),    # Waremme
        "76": (51.0000, 5.6400),    # Limburg
        "77": (50.7500, 5.2000),    # Hesbaye
        "78": (50.8300, 3.2700),    # Kortrijk
        "79": (50.7500, 3.6100),    # Waregem
        "80": (50.8100, 3.3200),    # West-Vlaanderen
        "81": (49.6700, 5.5500),    # Virton / Gaume
        "82": (50.0800, 5.0800),    # Rochefort
        "83": (50.0600, 5.5700),    # Saint-Hubert
        "84": (49.9300, 5.3500),    # Neufchâteau
        "85": (50.0900, 6.1300),    # Malmedy
        "86": (50.1400, 5.0000),    # Dinant
        "87": (50.7000, 5.8600),    # Verviers
        "88": (49.6800, 5.8100),    # Arlon
        "89": (50.9800, 5.5100),    # Hasselt est
        "90": (50.8000, 3.2700),    # Brugge
        "91": (51.2093, 3.2247),    # Brugge
        "92": (51.0300, 2.9000),    # Roeselare
        "93": (51.1600, 2.5400),    # Veurne
        "94": (51.1900, 3.0300),    # Torhout
        "95": (51.1000, 3.1200),    # Tielt
        "96": (51.0900, 3.1900),    # Tielt/Ruiselede
        "97": (50.8600, 2.8900),    # Ieper
        "98": (51.0400, 2.7100),    # Diksmuide
        "99": (51.3500, 3.2800),    # Knokke / Kust
    }

    pc = (user.postal_code or "").strip()
    country = (user.country or "").strip().upper()

    if country == "BE" and len(pc) >= 2:
        prefix = pc[:2]
        coords = _BE_POSTAL_PREFIXES.get(prefix)
        if coords:
            return coords

    # No match → don't overwrite existing coordinates
    return None, None


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
