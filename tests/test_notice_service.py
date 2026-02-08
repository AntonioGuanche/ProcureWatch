"""Tests for app.services.notice_service (BOSA + TED import pipeline).

Replaces:
  - tests/test_import_bosa.py
  - tests/test_import_ted.py
  - tests/test_import_ted_integration.py
  - tests/test_sync_ted.py
"""
import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.notice import NoticeSource, ProcurementNotice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.models.notice_lot import NoticeLot
from app.services.notice_service import (
    NoticeService,
    _extract_cpv_main_code,
    _extract_organisation_names,
    _extract_ted_organisation_names,
    _extract_title,
    _map_ted_item_to_notice,
    _safe_date,
    _safe_datetime,
    _ted_pick_text,
    _ted_source_id,
)


@pytest.fixture()
def db():
    """In-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    yield session
    session.close()
    engine.dispose()


# ── BOSA import ──────────────────────────────────────────────────────


BOSA_ITEM_MINIMAL = {
    "publicationWorkspaceId": "ws-001",
    "dossier": {"titles": [{"language": "FR", "text": "Travaux de voirie"}]},
    "cpvMainCode": {"code": "45233120-6"},
    "publicationDate": "2026-01-15",
    "noticeType": "CONTRACT_NOTICE",
    "organisation": {
        "organisationNames": [
            {"language": "FR", "text": "Ville de Bruxelles"},
        ],
        "organisationId": "org-123",
    },
}


def test_bosa_import_creates_notice(db: Session):
    svc = NoticeService(db)
    stats = asyncio.run(
        svc.import_from_eproc_search([BOSA_ITEM_MINIMAL], fetch_details=False)
    )
    assert stats["created"] == 1
    assert stats["updated"] == 0
    assert stats["errors"] == []

    notice = db.query(ProcurementNotice).one()
    assert notice.source_id == "ws-001"
    assert notice.source == NoticeSource.BOSA_EPROC.value
    assert notice.title == "Travaux de voirie"
    assert notice.cpv_main_code == "45233120-6"
    assert notice.organisation_id == "org-123"
    assert notice.organisation_names == {"FR": "Ville de Bruxelles"}


def test_bosa_import_dedupes_by_source_id(db: Session):
    svc = NoticeService(db)
    asyncio.run(svc.import_from_eproc_search([BOSA_ITEM_MINIMAL], fetch_details=False))

    # Second import with updated title
    updated_item = {
        **BOSA_ITEM_MINIMAL,
        "dossier": {"titles": [{"language": "FR", "text": "Travaux modifiés"}]},
    }
    stats = asyncio.run(
        svc.import_from_eproc_search([updated_item], fetch_details=False)
    )
    assert stats["created"] == 0
    assert stats["updated"] == 1

    notices = db.query(ProcurementNotice).all()
    assert len(notices) == 1
    assert notices[0].title == "Travaux modifiés"


def test_bosa_import_skips_no_workspace_id(db: Session):
    svc = NoticeService(db)
    stats = asyncio.run(
        svc.import_from_eproc_search([{"title": "orphan"}], fetch_details=False)
    )
    assert stats["skipped"] == 1
    assert stats["created"] == 0


def test_bosa_import_creates_lots_and_cpv(db: Session):
    item = {
        **BOSA_ITEM_MINIMAL,
        "allCpvCodes": [
            {"code": "45233120-6"},
            {"code": "71322000-1"},
            {"code": "45112000-5"},
        ],
        "lots": [
            {"number": "1", "titles": [{"language": "FR", "text": "Lot A"}]},
            {"number": "2", "titles": [{"language": "FR", "text": "Lot B"}]},
        ],
    }
    svc = NoticeService(db)
    asyncio.run(svc.import_from_eproc_search([item], fetch_details=False))

    notice = db.query(ProcurementNotice).one()
    lots = db.query(NoticeLot).filter(NoticeLot.notice_id == notice.id).all()
    cpvs = db.query(NoticeCpvAdditional).filter(NoticeCpvAdditional.notice_id == notice.id).all()

    assert len(lots) == 2
    assert {l.lot_number for l in lots} == {"1", "2"}
    # Additional CPV = all codes minus main (45233120-6)
    assert len(cpvs) >= 1
    cpv_codes = {c.cpv_code for c in cpvs}
    assert "71322000-1" in cpv_codes or "45112000-5" in cpv_codes


def test_bosa_import_empty_list(db: Session):
    svc = NoticeService(db)
    stats = asyncio.run(svc.import_from_eproc_search([], fetch_details=False))
    assert stats["created"] == 0


# ── TED import ───────────────────────────────────────────────────────


TED_ITEM_MINIMAL = {
    "publication-number": "2026/S 012-034567",
    "notice-title": {"eng": "Road construction services"},
    "main-classification-proc": "45233120-6",
    "publication-date": "2026-01-15",
    "buyer-name": "City of Brussels",
    "notice-type": "cn-standard",
    "buyer-country": "BEL",
}


def test_ted_import_creates_notice(db: Session):
    svc = NoticeService(db)
    stats = asyncio.run(
        svc.import_from_ted_search([TED_ITEM_MINIMAL], fetch_details=False)
    )
    assert stats["created"] == 1
    assert stats["errors"] == []

    notice = db.query(ProcurementNotice).one()
    assert notice.source_id == "2026/S 012-034567"
    assert notice.source == NoticeSource.TED_EU.value
    assert notice.title == "Road construction services"
    assert notice.cpv_main_code == "45233120-6"
    assert notice.organisation_names == {"default": "City of Brussels"}


def test_ted_import_dedupes_by_source_id(db: Session):
    svc = NoticeService(db)
    asyncio.run(svc.import_from_ted_search([TED_ITEM_MINIMAL], fetch_details=False))

    updated = {**TED_ITEM_MINIMAL, "notice-title": "Updated title"}
    stats = asyncio.run(svc.import_from_ted_search([updated], fetch_details=False))
    assert stats["created"] == 0
    assert stats["updated"] == 1
    assert db.query(ProcurementNotice).one().title == "Updated title"


def test_ted_import_skips_no_source_id(db: Session):
    svc = NoticeService(db)
    stats = asyncio.run(
        svc.import_from_ted_search([{"title": "orphan"}], fetch_details=False)
    )
    assert stats["skipped"] == 1


def test_ted_import_multiple_notices(db: Session):
    items = [
        {**TED_ITEM_MINIMAL, "publication-number": f"2026/S 01{i}-000{i}"} for i in range(5)
    ]
    svc = NoticeService(db)
    stats = asyncio.run(svc.import_from_ted_search(items, fetch_details=False))
    assert stats["created"] == 5
    assert db.query(ProcurementNotice).count() == 5


# ── Mapping helpers ──────────────────────────────────────────────────


def test_ted_source_id_publication_number():
    assert _ted_source_id({"publication-number": "2026/S 001-123"}) == "2026/S 001-123"


def test_ted_source_id_fallback_notice_id():
    assert _ted_source_id({"noticeId": "abc-123"}) == "abc-123"


def test_ted_source_id_none_for_empty():
    assert _ted_source_id({}) is None


def test_ted_pick_text_string():
    assert _ted_pick_text("Hello") == "Hello"


def test_ted_pick_text_multilang_prefers_eng():
    assert _ted_pick_text({"fra": "Bonjour", "eng": "Hello"}) == "Hello"


def test_ted_pick_text_none():
    assert _ted_pick_text(None) is None


def test_extract_cpv_main_code_object():
    assert _extract_cpv_main_code({"cpvMainCode": {"code": "45000000-7"}}, None) == "45000000-7"


def test_extract_cpv_main_code_string():
    assert _extract_cpv_main_code({"cpvMainCode": "45000000-7"}, None) == "45000000-7"


def test_extract_cpv_main_code_none():
    assert _extract_cpv_main_code({}, None) is None


def test_extract_title_from_dossier_titles():
    item = {"dossier": {"titles": [{"language": "FR", "text": "Mon titre"}]}}
    assert _extract_title(item, None) == "Mon titre"


def test_extract_title_string():
    assert _extract_title({"title": "Simple"}, None) == "Simple"


def test_extract_organisation_names_bosa():
    item = {
        "organisation": {
            "organisationNames": [
                {"language": "FR", "text": "Ville de Liège"},
                {"language": "NL", "text": "Stad Luik"},
            ]
        }
    }
    names = _extract_organisation_names(item, None)
    assert names == {"FR": "Ville de Liège", "NL": "Stad Luik"}


def test_ted_organisation_names_string():
    names = _extract_ted_organisation_names({"buyer-name": "SNCB"})
    assert names == {"default": "SNCB"}


def test_ted_organisation_names_multilang():
    names = _extract_ted_organisation_names(
        {"buyer-name": {"fra": ["Ville de Gand"], "eng": ["City of Ghent"]}}
    )
    assert names is not None
    assert "fra" in names or "eng" in names


def test_safe_date_iso_string():
    d = _safe_date("2026-01-15")
    assert d is not None
    assert d.year == 2026 and d.month == 1 and d.day == 15


def test_safe_datetime_iso():
    dt = _safe_datetime("2026-01-15T10:30:00Z")
    assert dt is not None
    assert dt.year == 2026


# ── import_from_all_sources ──────────────────────────────────────────


def test_import_from_all_sources_bosa_only(db: Session):
    """Test import_from_all_sources with BOSA only."""
    svc = NoticeService(db)

    fake_bosa_result = {
        "json": {"publications": [BOSA_ITEM_MINIMAL]},
    }

    with patch(
        "app.services.notice_service.search_publications_bosa",
        return_value=fake_bosa_result,
    ):
        result = asyncio.run(
            svc.import_from_all_sources(
                {"term": "test"}, fetch_details=False, sources=["BOSA"]
            )
        )

    assert result["bosa"]["created"] == 1
    assert result["ted"]["created"] == 0
    assert result["total"]["created"] == 1


def test_import_from_all_sources_ted_only(db: Session):
    """Test import_from_all_sources with TED only."""
    svc = NoticeService(db)

    fake_ted_result = {"notices": [TED_ITEM_MINIMAL]}

    with patch(
        "app.services.notice_service.search_ted_notices_app",
        return_value=fake_ted_result,
    ):
        result = asyncio.run(
            svc.import_from_all_sources(
                {"term": "test"}, fetch_details=False, sources=["TED"]
            )
        )

    assert result["ted"]["created"] == 1
    assert result["bosa"]["created"] == 0
    assert result["total"]["created"] == 1
