"""Ingest tests for sync_notice_details: mock get_publication_detail, verify DB upserts (offline)."""
import os


pytestmark = pytest.mark.integration

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_sync_notice_details.db"

import json
from unittest.mock import patch

import pytest

from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.models.notice import Notice
from app.models.notice_detail import NoticeDetail
from app.models.notice_lot import NoticeLot
from app.models.notice_document import NoticeDocument


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


FAKE_DETAIL = {
    "dossier": {
        "lots": [
            {"lotNumber": "1", "title": "Lot 1", "cpvCode": {"code": "45"}},
        ],
        "documents": [
            {"url": "https://example.com/doc.pdf", "title": "Doc"},
        ],
    },
}


def test_sync_notice_details_mock_fetch(db_schema):
    """With mocked get_publication_detail, sync stores detail and upserts lots/documents."""
    db = SessionLocal()
    try:
        n = Notice(
            source="BOSA_EPROC",
            source_id="PPP-FAKE-001",
            publication_workspace_id="ws-PPP-FAKE-001",
            title="Fake Notice",
            url="https://example.com/1",
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        notice_id = n.id
    finally:
        db.close()

    with patch("ingest.sync_notice_details.get_publication_detail", return_value=FAKE_DETAIL):
        import sys
        from ingest.sync_notice_details import main
        old_argv = list(sys.argv)
        sys.argv = ["sync_notice_details.py", "--notice-id", notice_id]
        try:
            exit_code = main()
        finally:
            sys.argv = old_argv
        assert exit_code == 0

    db = SessionLocal()
    try:
        detail = db.query(NoticeDetail).filter(NoticeDetail.notice_id == notice_id).first()
        assert detail is not None
        assert detail.raw_json is not None
        data = json.loads(detail.raw_json)
        assert data.get("dossier", {}).get("lots") is not None

        lots = db.query(NoticeLot).filter(NoticeLot.notice_id == notice_id).all()
        assert len(lots) == 1
        assert lots[0].lot_number == "1"
        assert lots[0].title == "Lot 1"

        docs = db.query(NoticeDocument).filter(NoticeDocument.notice_id == notice_id).all()
        assert len(docs) == 1
        assert docs[0].url == "https://example.com/doc.pdf"
        assert docs[0].title == "Doc"
    finally:
        db.close()
