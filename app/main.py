"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import auth, filters, health, notices
from app.api.routes import watchlists_mvp as watchlists

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
)

# Configure CORS for Lovable frontend + local/production
_cors_origins = [
    "http://localhost:3000",
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

# Include routers
app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(filters.router, prefix="/api")
app.include_router(notices.router, prefix="/api")
app.include_router(watchlists.router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"name": settings.app_name, "status": "running"}
