"""Tests for import_ted: fake raw TED JSON, temp SQLite; assert source=ted.europa.eu, dedupe, url set (offline)."""
import os
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Use temp DB before importing app.db (settings read DATABASE_URL)
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_import_ted.db"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional


# Minimal raw TED JSON as saved by sync_ted.py (metadata + json.notices)
FAKE_RAW_TED = {
    "metadata": {"term": "solar", "page": 1, "pageSize": 2},
    "json": {
        "notices": [
            {
                "noticeId": "TED-NOTICE-001",
                "title": "Solar panels supply",
                "contractingAuthority": {"name": "Ministry of Energy"},
                "country": "DE",
                "publicationDate": "2026-02-01T00:00:00Z",
                "deadlineDate": "2026-03-01T23:59:00Z",
                "mainCpv": {"code": "45000000"},
                "procedureType": "OPEN",
            },
            {
                "noticeId": "TED-NOTICE-002",
                "title": "PV installation works",
                "buyer": "City Council",
                "publicationDate": "2026-02-02",
                "mainCpv": {"code": "45310000"},
            },
        ],
        "totalCount": 2,
    },
}


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def raw_ted_file(tmp_path):
    """Write fake raw TED JSON to a temp file; return path."""
    path = tmp_path / "ted_fake.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(FAKE_RAW_TED, f, indent=2)
    return path


def test_import_ted_inserts_notices_with_source_and_url(db_schema, raw_ted_file):
    """Imported notices have source=ted.europa.eu and non-empty url."""
    from ingest.import_ted import import_file

    # Start clean so we get 2 new inserts (test-order independent)
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    imported_new, imported_updated, errors = import_file(raw_ted_file)
    assert imported_new == 2
    assert imported_updated == 0
    assert errors == 0

    db = SessionLocal()
    try:
        notices = db.query(Notice).filter(Notice.source == "ted.europa.eu").order_by(Notice.source_id).all()
        assert len(notices) == 2
        ids = [n.source_id for n in notices]
        assert "TED-NOTICE-001" in ids
        assert "TED-NOTICE-002" in ids
        for n in notices:
            assert n.source == "ted.europa.eu"
            assert n.title in ("Solar panels supply", "PV installation works")
            assert n.url and isinstance(n.url, str) and n.url.startswith("http")
            assert "ted.europa.eu" in n.url
    finally:
        db.close()


def test_import_ted_dedupe_updates_last_seen_at(db_schema, raw_ted_file):
    """Second import of same file updates last_seen_at / updated_at (dedupe)."""
    from ingest.import_ted import import_file

    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    import_file(raw_ted_file)
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-NOTICE-001",
        ).first()
        assert notice is not None
        first_seen = notice.first_seen_at
        last_seen_before = notice.last_seen_at
        updated_before = notice.updated_at
    finally:
        db.close()

    # Second import (same file): touch semantics -> imported_updated=2, last_seen_at/updated_at refresh
    imported_new, imported_updated, errors = import_file(raw_ted_file)
    assert imported_new == 0
    assert imported_updated == 2
    assert errors == 0

    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-NOTICE-001",
        ).first()
        assert notice is not None
        assert notice.first_seen_at == first_seen  # unchanged
        assert notice.last_seen_at >= last_seen_before  # updated
        assert notice.updated_at >= updated_before  # updated
    finally:
        db.close()


def test_import_ted_buyer_country_maps_to_notice_country(db_schema, tmp_path):
    """TED notice with buyer-country=BE results in Notice.country=='BE'."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-BE-123",
                    "noticeId": "TED-BE-123",
                    "title": "Belgian contract",
                    "buyer-name": "Federal Agency",
                    "buyer-country": "BE",
                    "publicationDate": "2026-02-01",
                    "mainCpv": {"code": "45000000"},
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_be.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    imported_new, imported_updated, errors = import_file(path)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-BE-123",
        ).first()
        assert notice is not None
        assert notice.country == "BE"
    finally:
        db.close()
