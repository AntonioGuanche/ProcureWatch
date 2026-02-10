"""JWT token helpers + password hashing (bcrypt via passlib)."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(sub: str, user_id: str, name: str | None = None) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expiry_days)
    payload: dict[str, Any] = {
        "sub": sub,
        "user_id": user_id,
        "exp": expire,
        "name": name or sub,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_reset_token(user_id: str, email: str) -> str:
    """Create a short-lived JWT for password reset (1 hour)."""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload: dict[str, Any] = {
        "sub": email,
        "user_id": user_id,
        "purpose": "password_reset",
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_reset_token(token: str) -> dict[str, Any] | None:
    """Decode password reset token. Returns payload only if purpose=password_reset."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("purpose") != "password_reset":
            return None
        return payload
    except JWTError:
        return None


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate JWT; return payload or None if invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None
