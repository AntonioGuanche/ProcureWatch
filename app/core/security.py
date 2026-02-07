"""JWT token helpers for mock auth (Lovable)."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(sub: str, user_id: str, name: str | None = None) -> str:
    """
    Create a JWT access token. Mock auth: sub=email, user_id and name in payload.
    """
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
