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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import engine
from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from ingest.import_ted import create_local_session


# Helper to get test sessionmaker
def _get_test_sessionmaker():
    """Get sessionmaker for test database."""
    test_db_url = os.environ["DATABASE_URL"]
    return create_local_session(test_db_url)


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
    """Create tables once for the module using test database."""
    # Use test database URL from environment
    test_db_url = os.environ["DATABASE_URL"]
    from sqlalchemy import create_engine
    test_engine = create_engine(test_db_url)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


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

    SessionLocal = _get_test_sessionmaker()
    
    # Start clean so we get 2 new inserts (test-order independent)
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    imported_new, imported_updated, errors = import_file(raw_ted_file, SessionLocal)
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
    
    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    import_file(raw_ted_file, SessionLocal)
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
    imported_new, imported_updated, errors = import_file(raw_ted_file, SessionLocal)
    assert imported_new == 0
    assert imported_updated == 2
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
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
    
    SessionLocal = _get_test_sessionmaker()

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

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
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


def test_import_ted_uses_publication_number_when_notice_id_missing(db_schema, tmp_path):
    """Missing noticeId does not block import when publication-number exists."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-PUB-999",
                    # No noticeId field here; source_id must fall back to publication-number
                    "title": "No noticeId but has publication-number",
                    "buyer-country": "FR",
                    "publicationDate": "2026-02-05",
                    "mainCpv": {"code": "45000000"},
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_pub_only.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-PUB-999",
        ).first()
        assert notice is not None
        assert notice.title.startswith("No noticeId")
        assert notice.country == "FR"
    finally:
        db.close()


def test_import_ted_maps_ted_search_api_fields(db_schema, tmp_path):
    """TED Search API fields (notice-title, buyer-country, main-classification-proc) are correctly mapped."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "solar", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-SEARCH-001",
                    "notice-title": "Solar Panel Installation Project",
                    "buyer-country": "BE",
                    "main-classification-proc": "45261200",
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_search_fields.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-SEARCH-001",
        ).first()
        assert notice is not None
        assert notice.title == "Solar Panel Installation Project"
        assert notice.country == "BE"
        assert notice.cpv_main_code == "45261200"
    finally:
        db.close()


def test_import_ted_maps_main_classification_proc_dict(db_schema, tmp_path):
    """main-classification-proc as dict is correctly extracted."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-DICT-CPV-001",
                    "notice-title": "Test Notice",
                    "buyer-country": "FR",
                    "main-classification-proc": {"code": "71000000", "id": "71000000"},
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_dict_cpv.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-DICT-CPV-001",
        ).first()
        assert notice is not None
        assert notice.title == "Test Notice"
        assert notice.country == "FR"
        assert notice.cpv_main_code == "71000000"
    finally:
        db.close()


def test_import_ted_notice_title_dict_chooses_eng(db_schema, tmp_path):
    """notice-title as dict chooses ENG preferred, then FRA, then first non-empty."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-MULTILANG-001",
                    "notice-title": {"eng": "Solar Energy Project", "fra": "Projet d'énergie solaire", "deu": "Solarenergieprojekt"},
                    "buyer-country": "BE",
                    "main-classification-proc": "45000000",
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_multilang.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-MULTILANG-001",
        ).first()
        assert notice is not None
        assert notice.title == "Solar Energy Project"  # Should prefer ENG
    finally:
        db.close()


def test_import_ted_buyer_country_3_letter_normalized(db_schema, tmp_path):
    """buyer-country 3-letter code is normalized to alpha_2 if possible."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-3LETTER-001",
                    "notice-title": "Malta Contract",
                    "buyer-country": "MLT",  # 3-letter code for Malta
                    "main-classification-proc": "45000000",
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_3letter_country.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-3LETTER-001",
        ).first()
        assert notice is not None
        assert notice.country == "MT"  # Should normalize MLT to MT
    finally:
        db.close()


def test_normalize_country_list_fra(db_schema):
    """normalize_country(['FRA']) returns 'FR'."""
    from ingest.import_ted import normalize_country
    
    assert normalize_country(["FRA"]) == "FR"
    assert normalize_country(["FRA", "BEL"]) == "FR"  # First that normalizes
    assert normalize_country(("FRA",)) == "FR"
    assert normalize_country({"FRA"}) == "FR"


def test_normalize_country_list_be(db_schema):
    """normalize_country(['BE']) returns 'BE'."""
    from ingest.import_ted import normalize_country
    
    assert normalize_country(["BE"]) == "BE"
    assert normalize_country(["BE", "FR"]) == "BE"  # First that normalizes


def test_normalize_country_bel_string(db_schema):
    """normalize_country('BEL') returns 'BE'."""
    from ingest.import_ted import normalize_country
    
    assert normalize_country("BEL") == "BE"
    assert normalize_country("FRA") == "FR"
    assert normalize_country("DEU") == "DE"


def test_normalize_country_unknown_returns_none(db_schema):
    """normalize_country('XXX') returns None (not 'EU')."""
    from ingest.import_ted import normalize_country
    
    assert normalize_country("XXX") is None
    assert normalize_country("EU") is None  # Should not return 'EU'
    assert normalize_country(["XXX"]) is None


def test_import_ted_extract_cpv_from_classification_cpv(db_schema, tmp_path):
    """CPV extracted from classification-cpv field when main-classification-proc not present."""
    from ingest.import_ted import import_file

    raw = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-CLASS-CPV-001",
                    "notice-title": "Test Notice",
                    "buyer-country": "BE",
                    "classification-cpv": "45261200-5",  # CPV with check digit
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    path = tmp_path / "ted_class_cpv.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        db.query(Notice).filter(Notice.source == "ted.europa.eu").delete()
        db.commit()
    finally:
        db.close()

    SessionLocal = _get_test_sessionmaker()
    imported_new, imported_updated, errors = import_file(path, SessionLocal)
    assert imported_new == 1
    assert imported_updated == 0
    assert errors == 0

    SessionLocal = _get_test_sessionmaker()
    db = SessionLocal()
    try:
        notice = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            Notice.source_id == "TED-CLASS-CPV-001",
        ).first()
        assert notice is not None
        assert notice.cpv_main_code == "45261200"  # Should extract 8 digits
    finally:
        db.close()
