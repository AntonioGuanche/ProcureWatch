"""API tests for notice detail, lots, documents (TestClient + SQLite, offline)."""
import os
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_notice_detail_api.db"

import pytest

pytestmark = pytest.mark.integration
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import engine, SessionLocal
from app.models.base import Base
from app.models.notice import Notice
from app.models.notice_detail import NoticeDetail
from app.models.notice_lot import NoticeLot
from app.models.notice_document import NoticeDocument


@pytest.fixture(scope="function")
def db_setup():
    """Create test database tables; drop after test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_setup):
    """Test client."""
    return TestClient(app)


@pytest.fixture
def sample_notice(db_setup):
    """Insert a fake notice and return it."""
    db = SessionLocal()
    try:
        n = Notice(
            source="BOSA_EPROC",
            source_id="PPP-TEST-001",
            publication_workspace_id="ws-PPP-TEST-001",
            title="Test Notice",
            url="https://example.com/1",
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        return n
    finally:
        db.close()


def test_get_notice_detail_404(client: TestClient, sample_notice):
    """GET /api/notices/{id}/detail returns 404 when detail not stored."""
    resp = client.get(f"/api/notices/{sample_notice.id}/detail")
    assert resp.status_code == 404


def test_get_notice_detail_ok(client: TestClient, sample_notice):
    """GET /api/notices/{id}/detail returns raw_json and fetched_at when present."""
    db = SessionLocal()
    try:
        d = NoticeDetail(
            notice_id=sample_notice.id,
            source="BOSA_EPROC",
            source_id=sample_notice.source_id,
            raw_json='{"test": true}',
        )
        db.add(d)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/detail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_json"] == '{"test": true}'
    assert "fetched_at" in data


def test_get_notice_lots_empty(client: TestClient, sample_notice):
    """GET /api/notices/{id}/lots returns paginated empty list."""
    resp = client.get(f"/api/notices/{sample_notice.id}/lots?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert data["items"] == []


def test_get_notice_lots_with_data(client: TestClient, sample_notice):
    """GET /api/notices/{id}/lots returns paginated lots."""
    db = SessionLocal()
    try:
        lot = NoticeLot(
            notice_id=sample_notice.id,
            lot_number="1",
            title="Lot 1",
            cpv_code="45000000",
        )
        db.add(lot)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/lots?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["lot_number"] == "1"
    assert data["items"][0]["title"] == "Lot 1"
    assert data["items"][0]["cpv_code"] == "45000000"


def test_get_notice_documents_empty(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents returns paginated empty list."""
    resp = client.get(f"/api/notices/{sample_notice.id}/documents?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_get_notice_documents_with_data(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents returns paginated documents."""
    db = SessionLocal()
    try:
        doc = NoticeDocument(
            notice_id=sample_notice.id,
            title="Specs",
            url="https://example.com/spec.pdf",
            file_type="PDF",
        )
        db.add(doc)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/documents?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["url"] == "https://example.com/spec.pdf"
    assert data["items"][0]["title"] == "Specs"
    assert data["items"][0]["file_type"] == "PDF"


def test_get_notice_documents_includes_pipeline_fields(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents includes local_path and download/extraction status."""
    db = SessionLocal()
    try:
        doc = NoticeDocument(
            notice_id=sample_notice.id,
            title="Doc",
            url="https://example.com/f.pdf",
            file_type="PDF",
            local_path="/data/documents/n1/d1.pdf",
            download_status="ok",
            extraction_status="ok",
            extracted_text="Hello",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/documents?page=1&page_size=25")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["local_path"] == "/data/documents/n1/d1.pdf"
    assert items[0]["download_status"] == "ok"
    assert items[0]["extraction_status"] == "ok"


def test_get_notice_document_text_404_unknown_document(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents/{doc_id}/text returns 404 for unknown document."""
    resp = client.get(
        f"/api/notices/{sample_notice.id}/documents/00000000-0000-0000-0000-000000000001/text"
    )
    assert resp.status_code == 404


def test_get_notice_document_text_404_no_extracted_text(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents/{doc_id}/text returns 404 when no text stored."""
    db = SessionLocal()
    try:
        doc = NoticeDocument(
            notice_id=sample_notice.id,
            url="https://example.com/f.pdf",
            file_type="PDF",
            extracted_text=None,
            extraction_status=None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/documents/{doc_id}/text")
    assert resp.status_code == 404


def test_get_notice_document_text_ok(client: TestClient, sample_notice):
    """GET /api/notices/{id}/documents/{doc_id}/text returns extracted text and metadata."""
    db = SessionLocal()
    try:
        doc = NoticeDocument(
            notice_id=sample_notice.id,
            title="Spec PDF",
            url="https://example.com/spec.pdf",
            file_type="PDF",
            extracted_text="Sample extracted content here.",
            extraction_status="ok",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
    finally:
        db.close()

    resp = client.get(f"/api/notices/{sample_notice.id}/documents/{doc_id}/text")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == doc_id
    assert data["notice_id"] == sample_notice.id
    assert data["title"] == "Spec PDF"
    assert data["extracted_text"] == "Sample extracted content here."
    assert data["extraction_status"] == "ok"


def test_notice_detail_404_unknown_notice(client: TestClient):
    """GET /api/notices/{id}/detail returns 404 for unknown notice."""
    resp = client.get("/api/notices/00000000-0000-0000-0000-000000000000/detail")
    assert resp.status_code == 404
