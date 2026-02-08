"""Tests for BOSA import (ingest/import_bosa.py). Uses DATABASE_URL from conftest (test.db)."""
import json
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.db_url import get_default_db_url, resolve_db_url
from app.models.base import Base
from app.models.notice import Notice


def _test_db_url():
    return resolve_db_url(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///./test.db"))


@pytest.fixture(scope="module")
def db_schema():
    """Create tables on the same DB URL the importer uses (resolved), so both see the same schema."""
    url = _test_db_url()
    eng = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db(db_schema):
    """Fresh session on the same DB as the importer."""
    url = _test_db_url()
    SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=create_engine(url, pool_pre_ping=True))
    session = SessionLocalTest()
    session.query(Notice).delete()
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_import_bosa_single_publication(db):
    """Import a minimal BOSA JSON file produces one notice with source bosa.eprocurement."""
    from ingest.import_bosa import import_bosa_raw_files

    raw = {
        "json": {
            "publications": [
                {
                    "id": "bosa-test-123",
                    "title": "Test publication",
                    "contractingAuthority": "Test Authority",
                    "publicationDate": "2024-01-15T10:00:00Z",
                    "submissionDeadline": "2024-02-15T17:00:00Z",
                    "url": "https://public.fedservices.be/pub/123",
                }
            ]
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
        path = Path(f.name)
    try:
        db_url = get_default_db_url()
        created, updated, errors = import_bosa_raw_files([path], db_url=db_url)
        assert errors == 0
        assert created == 1 or updated == 1
    finally:
        path.unlink(missing_ok=True)

    notice = db.query(Notice).filter(Notice.source == "BOSA_EPROC", Notice.source_id == "bosa-test-123").first()
    assert notice is not None
    assert notice.title == "Test publication"
    assert notice.organisation_names == {"default": "Test Authority"}
    assert "BE" in (notice.nuts_codes or [])
    assert notice.url == "https://public.fedservices.be/pub/123"


def test_import_bosa_uses_items_key(db):
    """BOSA response can use 'items' key instead of 'publications'."""
    from ingest.import_bosa import import_bosa_raw_files

    raw = {
        "json": {
            "items": [
                {
                    "publicationId": "bosa-items-456",
                    "name": "Item-based notice",
                }
            ]
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
        path = Path(f.name)
    try:
        db_url = get_default_db_url()
        created, updated, errors = import_bosa_raw_files([path], db_url=db_url)
        assert errors == 0
        assert created == 1
    finally:
        path.unlink(missing_ok=True)

    notice = db.query(Notice).filter(Notice.source == "BOSA_EPROC", Notice.source_id == "bosa-items-456").first()
    assert notice is not None
    assert notice.title == "Item-based notice"
    assert "BE" in (notice.nuts_codes or [])
