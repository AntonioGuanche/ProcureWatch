"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import admin, favorites, auth, filters, health, notices
from app.api.routes import dashboard
from app.api.routes import admin_stats
from app.api.routes import watchlists_mvp as watchlists
from app.api.routes.admin_digest import router as admin_digest_router
from app.api.routes.billing import router as billing_router

# Setup logging
setup_logging()

# Frontend build directory
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: scheduler management."""
    from app.services.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for Lovable frontend + local/production
_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "https://lovable.app",
    "https://lovable.dev",
    "https://procurewatch.app",
]
# Check if wildcard allowed (e.g. ALLOWED_ORIGINS=* from Railway)
if "*" in settings.allowed_origins_list:
    _cors_origins_final = ["*"]
else:
    _cors_origins_final = _cors_origins + [
        o for o in settings.allowed_origins_list if o not in ["**", ""]
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_final,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"https://.*\.lovable\.(app|dev)",
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Include API routers
app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(filters.router, prefix="/api")
app.include_router(notices.router, prefix="/api")
app.include_router(watchlists.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_stats.router, prefix="/api")
app.include_router(favorites.router, prefix="/api")
app.include_router(admin_digest_router, prefix="/api")
app.include_router(billing_router, prefix="/api")

# Public endpoints (no auth)
from app.api.routes import public as public_routes
app.include_router(public_routes.router, prefix="/api")


# ── SPA frontend serving ────────────────────────────────────────────

if WEB_DIST.is_dir():
    # Serve static assets (JS, CSS, images) under /assets
    assets_dir = WEB_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve frontend: try exact file, fallback to index.html (SPA routing)."""
        # Don't serve frontend for API routes (already handled above)
        if full_path.startswith("api/"):
            return {"detail": "Not found"}

        # Try serving the exact file (favicon.ico, robots.txt, etc.)
        file_path = WEB_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))

        # Fallback: serve index.html for SPA client-side routing
        index = WEB_DIST / "index.html"
        if index.is_file():
            return FileResponse(str(index))

        return {"detail": "Frontend not built"}
else:
    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint (no frontend build available)."""
        return {"name": settings.app_name, "status": "running"}
