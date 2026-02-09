"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import admin, auth, filters, health, notices
from app.api.routes import dashboard
from app.api.routes import watchlists_mvp as watchlists

# Setup logging
setup_logging()


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

# Include routers
app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(filters.router, prefix="/api")
app.include_router(notices.router, prefix="/api")
app.include_router(watchlists.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"name": settings.app_name, "status": "running"}
