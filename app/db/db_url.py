"""Database URL resolution utilities."""
import os
from pathlib import Path


def resolve_db_url(db_url: str) -> str:
    """
    Resolve relative SQLite database URLs to absolute paths (Windows-safe).
    If db_url is sqlite:///./dev.db or sqlite:///./something.db (relative), resolve to absolute path.
    Keep non-sqlite URLs unchanged.
    """
    if not db_url.startswith("sqlite"):
        return db_url
    
    # Parse sqlite:///./path or sqlite+pysqlite:///./path
    if ":///./" in db_url:
        # Relative path: sqlite:///./dev.db -> resolve to absolute
        parts = db_url.split(":///./", 1)
        if len(parts) == 2:
            prefix = parts[0] + ":///"
            relative_path = parts[1]
            # Resolve relative to project root (where alembic.ini lives)
            project_root = Path(__file__).resolve().parent.parent.parent
            absolute_path = (project_root / relative_path).resolve()
            return f"{prefix}{absolute_path.as_posix()}"
    
    # Already absolute or other format: return as-is
    return db_url


def get_default_db_url() -> str:
    """Get default database URL: DATABASE_URL env var or sqlite:///./dev.db."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return resolve_db_url(db_url)
    return resolve_db_url("sqlite:///./dev.db")
