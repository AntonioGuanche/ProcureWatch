"""Authentication & authorization dependencies.

- require_admin_key: protects /admin endpoints via X-Admin-Key header
- RateLimiter: simple in-memory per-IP rate limiting
"""
import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Admin API key ────────────────────────────────────────────────────

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(
    request: Request,
    api_key: Optional[str] = Security(_admin_key_header),
) -> str:
    """
    Dependency: require valid ADMIN_API_KEY via X-Admin-Key header.
    If ADMIN_API_KEY is not set (empty), admin endpoints are OPEN (dev mode).
    """
    configured_key = settings.admin_api_key

    # Dev mode: no key configured → allow all (with warning log)
    if not configured_key:
        logger.warning(
            "ADMIN_API_KEY not set — admin endpoints are UNPROTECTED. "
            "Set ADMIN_API_KEY in Railway environment variables for production."
        )
        return "dev-mode"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Admin-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != configured_key:
        logger.warning("Invalid admin API key attempt from %s", request.client.host if request.client else "unknown")
        raise HTTPException(
            status_code=403,
            detail="Invalid admin API key",
        )

    return api_key


# ── Rate limiter (in-memory, per IP) ────────────────────────────────

class RateLimiter:
    """
    Simple sliding-window rate limiter. No Redis needed.
    Tracks request timestamps per IP; rejects with 429 when limit exceeded.
    
    Usage as FastAPI dependency:
        limiter = RateLimiter(per_minute=60)
        @app.get("/search", dependencies=[Depends(limiter)])
    """

    def __init__(self, per_minute: Optional[int] = None, burst: Optional[int] = None):
        self.per_minute = per_minute or settings.rate_limit_per_minute
        self.burst = burst or settings.rate_limit_burst
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For (Railway proxy)."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, now: float) -> None:
        """Periodically remove old entries (every 60s)."""
        if now - self._last_cleanup < 60:
            return
        cutoff = now - 60
        stale_keys = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale_keys:
            del self._hits[k]
        self._last_cleanup = now

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        self._cleanup(now)

        ip = self._client_ip(request)
        window = self._hits[ip]

        # Remove timestamps outside the 60s window
        cutoff = now - 60
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= self.per_minute:
            retry_after = int(60 - (now - window[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.per_minute} requests/minute. Retry in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)


# Pre-built instances
rate_limit_public = RateLimiter()
rate_limit_admin = RateLimiter(per_minute=30)
