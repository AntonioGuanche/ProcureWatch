"""Pytest configuration and shared fixtures.

Set DATABASE_URL before any app module imports to use SQLite for tests.
Provides reusable fixtures: db session, notice factory, seeding helpers.
"""
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Force SQLite before any app import
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.db"
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("BOSA_CLIENT_ID", "test")
os.environ.setdefault("BOSA_CLIENT_SECRET", "test")

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource


# ── Database fixtures ────────────────────────────────────────────────

@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    """SQLAlchemy session bound to in-memory SQLite."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


# ── Notice factory ───────────────────────────────────────────────────

def make_notice(**kwargs) -> ProcurementNotice:
    """Factory for ProcurementNotice with sensible defaults."""
    uid = uuid.uuid4().hex[:8]
    defaults = {
        "id": str(uuid.uuid4()),
        "source_id": f"src-{uid}",
        "source": NoticeSource.BOSA_EPROC.value,
        "publication_workspace_id": f"ws-{uid}",
        "title": "Default notice title",
        "publication_date": date(2024, 6, 15),
    }
    defaults.update(kwargs)
    return ProcurementNotice(**defaults)


def seed_notices(db, notices: list[ProcurementNotice]):
    """Add notices to session and commit."""
    for n in notices:
        db.add(n)
    db.commit()


# ── Markers ──────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks slow tests")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "unit: marks unit tests")
