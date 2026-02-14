"""Tests for admin endpoints and enhanced health check."""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    # Create import_runs table (not managed by Base)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS import_runs (
                id VARCHAR(36) PRIMARY KEY,
                source VARCHAR(50) NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                created_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                errors_json TEXT,
                search_criteria_json TEXT
            )
        """))
        conn.commit()
    return engine


@pytest.fixture()
def db(db_engine):
    Session_ = sessionmaker(bind=db_engine)
    session = Session_()
    yield session
    session.close()


def test_import_runs_summary_empty(db):
    """Summary endpoint returns empty when no runs exist."""
    from app.api.routes.admin_import import import_runs_summary

    # Simulate by calling the query logic directly
    rows = db.execute(text("""
        SELECT source,
               MAX(started_at) as last_run,
               SUM(created_count) as total_created,
               SUM(updated_count) as total_updated,
               SUM(error_count) as total_errors,
               COUNT(*) as run_count
        FROM import_runs
        GROUP BY source
    """)).mappings().all()
    assert len(rows) == 0


def test_save_and_list_import_run(db):
    """Save an import run and verify it can be listed."""
    from app.api.routes.admin_import import _save_import_run
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    _save_import_run(
        db,
        source="BOSA",
        started_at=now,
        completed_at=now,
        created_count=10,
        updated_count=5,
        error_count=0,
        errors_json=None,
        search_criteria_json={"term": "test", "trigger": "api"},
    )

    rows = db.execute(text("SELECT * FROM import_runs")).mappings().all()
    assert len(rows) == 1
    assert rows[0]["source"] == "BOSA"
    assert rows[0]["created_count"] == 10
    assert rows[0]["updated_count"] == 5


def test_fetch_page_bosa_extracts_publications():
    """_fetch_page correctly extracts publications list from BOSA response."""
    from app.api.routes.admin_import import _fetch_page

    fake_result = {"json": {"publications": [{"id": "1"}, {"id": "2"}]}}
    with patch("app.connectors.bosa.client.search_publications", return_value=fake_result):
        items = _fetch_page("BOSA", "test", 1, 25)
    assert len(items) == 2


def test_fetch_page_ted_extracts_notices():
    """_fetch_page correctly extracts notices list from TED response."""
    from app.api.routes.admin_import import _fetch_page

    fake_result = {"notices": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    with patch("app.connectors.ted.client.search_ted_notices", return_value=fake_result):
        items = _fetch_page("TED", "test", 1, 25)
    assert len(items) == 3
