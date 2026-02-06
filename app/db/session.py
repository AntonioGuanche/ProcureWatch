"""Database session management."""
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.db.base import Base
from app.db.db_url import resolve_db_url

# Resolve database URL (handle relative SQLite paths)
resolved_db_url = resolve_db_url(settings.database_url)

# Create engine with SSL support
engine = create_engine(
    resolved_db_url,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL query logging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI routes to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Check if database connection is available."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# Create tables (for development, migrations handle this in production)
def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
