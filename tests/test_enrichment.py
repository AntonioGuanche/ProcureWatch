"""Tests for Phase 8: data enrichment service."""
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.notice import ProcurementNotice, NoticeSource


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _notice(**kwargs) -> ProcurementNotice:
    defaults = {
        "id": str(uuid.uuid4()),
        "source_id": f"src-{uuid.uuid4().hex[:8]}",
        "source": NoticeSource.BOSA_EPROC.value,
        "publication_workspace_id": f"ws-{uuid.uuid4().hex[:8]}",
        "title": "Test notice",
        "publication_date": date(2024, 6, 1),
        "created_at": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return ProcurementNotice(**defaults)


# ── TED enrichment ────────────────────────────────────────────────


class TestTedEnrichment:
    def test_description_from_raw(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            description=None,
            raw_data={"description-lot": {"fra": "Travaux de construction"}},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "description" in updated
        assert n.description == "Travaux de construction"

    def test_notice_type_from_raw(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            notice_type=None,
            raw_data={"notice-type": "cn-standard"},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "notice_type" in updated
        assert n.notice_type == "cn-standard"

    def test_url_generation(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            url=None,
            raw_data={},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "url" in updated
        assert n.url == "https://ted.europa.eu/en/notice/-/detail/12345-2024"

    def test_org_names_from_buyer(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            organisation_names=None,
            raw_data={"buyer-name": {"fra": ["Ville de Bruxelles"], "eng": ["City of Brussels"]}},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "organisation_names" in updated
        assert "fra" in n.organisation_names
        assert "eng" in n.organisation_names

    def test_nuts_from_raw(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            nuts_codes=None,
            raw_data={"place-of-performance": ["BE100", "BE241"]},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "nuts_codes" in updated
        assert n.nuts_codes == ["BE100", "BE241"]

    def test_no_overwrite_existing(self, db):
        from app.services.enrichment_service import _enrich_ted_notice

        n = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="12345-2024",
            description="Already filled",
            url="https://existing.url",
            raw_data={"description-lot": "New desc"},
        )
        db.add(n)
        db.commit()

        updated = _enrich_ted_notice(n)
        assert "description" not in updated
        assert n.description == "Already filled"
        assert "url" not in updated


# ── BOSA enrichment ──────────────────────────────────────────────


class TestBosaEnrichment:
    def test_org_names_from_raw(self, db):
        from app.services.enrichment_service import _enrich_bosa_notice

        n = _notice(
            organisation_names=None,
            raw_data={
                "organisation": {
                    "organisationNames": [
                        {"language": "FR", "text": "SPF Finances"},
                        {"language": "NL", "text": "FOD Financiën"},
                    ]
                }
            },
        )
        db.add(n)
        db.commit()

        updated = _enrich_bosa_notice(n)
        assert "organisation_names" in updated
        assert n.organisation_names["FR"] == "SPF Finances"
        assert n.organisation_names["NL"] == "FOD Financiën"

    def test_url_generation(self, db):
        from app.services.enrichment_service import _enrich_bosa_notice

        ws_id = "abc-123-def"
        n = _notice(
            url=None,
            publication_workspace_id=ws_id,
            raw_data={},
        )
        db.add(n)
        db.commit()

        updated = _enrich_bosa_notice(n)
        assert "url" in updated
        assert ws_id in n.url

    def test_notice_type_from_raw(self, db):
        from app.services.enrichment_service import _enrich_bosa_notice

        n = _notice(
            notice_type=None,
            raw_data={"noticeType": "CONTRACT_NOTICE"},
        )
        db.add(n)
        db.commit()

        updated = _enrich_bosa_notice(n)
        assert n.notice_type == "CONTRACT_NOTICE"


# ── Backfill orchestrator ────────────────────────────────────────


class TestBackfill:
    def test_backfill_enriches_multiple(self, db):
        from app.services.enrichment_service import backfill_from_raw_data

        n1 = _notice(
            source=NoticeSource.TED_EU.value,
            source_id="111-2024",
            url=None,
            raw_data={"notice-type": "cn-standard"},
        )
        n2 = _notice(
            source=NoticeSource.BOSA_EPROC.value,
            url=None,
            organisation_names=None,
            raw_data={"noticeType": "PRIOR_INFORMATION"},
        )
        db.add_all([n1, n2])
        db.commit()

        result = backfill_from_raw_data(db)
        assert result["processed"] == 2
        assert result["enriched"] == 2
        assert result["fields_updated"].get("url", 0) >= 2

    def test_backfill_source_filter(self, db):
        from app.services.enrichment_service import backfill_from_raw_data

        n1 = _notice(source=NoticeSource.TED_EU.value, source_id="111-2024", url=None, raw_data={})
        n2 = _notice(source=NoticeSource.BOSA_EPROC.value, url=None, raw_data={})
        db.add_all([n1, n2])
        db.commit()

        result = backfill_from_raw_data(db, source=NoticeSource.TED_EU.value)
        assert result["processed"] == 1

    def test_backfill_limit(self, db):
        from app.services.enrichment_service import backfill_from_raw_data

        for i in range(5):
            db.add(_notice(source=NoticeSource.TED_EU.value, source_id=f"{i}-2024", url=None, raw_data={}))
        db.commit()

        result = backfill_from_raw_data(db, limit=2)
        assert result["processed"] == 2

    def test_backfill_skips_no_raw_data(self, db):
        from app.services.enrichment_service import backfill_from_raw_data

        n1 = _notice(raw_data=None)
        db.add(n1)
        db.commit()

        result = backfill_from_raw_data(db)
        # SQLite stores JSON None as json-null (not SQL NULL), so it may still
        # be "processed" without extracting anything. The key assertion is that
        # no fields were actually enriched.
        assert result["enriched"] == 0


# ── Data quality report ──────────────────────────────────────────


class TestDataQuality:
    def test_report_structure(self, db):
        from app.services.enrichment_service import get_data_quality_report

        n1 = _notice(title="A", description="Desc", url="https://x.com")
        n2 = _notice(title="B", description=None, url=None)
        db.add_all([n1, n2])
        db.commit()

        report = get_data_quality_report(db)
        assert report["total"] == 2
        assert "title" in report["fields"]
        assert report["fields"]["title"]["filled"] == 2
        assert report["fields"]["title"]["pct"] == 100.0
        assert report["fields"]["description"]["filled"] == 1
        assert report["fields"]["description"]["pct"] == 50.0

    def test_report_per_source(self, db):
        from app.services.enrichment_service import get_data_quality_report

        n1 = _notice(source=NoticeSource.BOSA_EPROC.value, title="A", url="x")
        n2 = _notice(source=NoticeSource.TED_EU.value, title="B", url=None)
        db.add_all([n1, n2])
        db.commit()

        report = get_data_quality_report(db)
        assert NoticeSource.BOSA_EPROC.value in report["per_source"]
        assert NoticeSource.TED_EU.value in report["per_source"]

    def test_empty_db(self, db):
        from app.services.enrichment_service import get_data_quality_report

        report = get_data_quality_report(db)
        assert report["total"] == 0
