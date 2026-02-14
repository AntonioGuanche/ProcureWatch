"""Tests for searchable text building."""
import json
import os


pytestmark = pytest.mark.integration

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_searchable_text.db"

import pytest

from app.models.base import Base
from app.models.notice import Notice
from app.models.notice_detail import NoticeDetail
from app.db.session import SessionLocal, engine
from app.utils.searchable_text import build_searchable_text, pick_text


@pytest.fixture(scope="module")
def db_schema():
    """Create tables once for the module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_pick_text_string():
    """pick_text returns string as-is."""
    assert pick_text("Hello World") == "Hello World"
    assert pick_text("  spaced  ") == "spaced"
    assert pick_text("") is None


def test_pick_text_dict_prefers_eng():
    """pick_text from dict prefers ENG, then FRA, then first non-empty."""
    assert pick_text({"eng": "English", "fra": "French"}) == "English"
    assert pick_text({"fra": "French", "deu": "German"}) == "French"
    assert pick_text({"deu": "German", "ita": "Italian"}) == "German"


def test_pick_text_list_returns_first():
    """pick_text from list returns first non-empty item."""
    assert pick_text(["first", "second"]) == "first"
    assert pick_text(["", "second"]) == "second"
    assert pick_text([{"eng": "English"}, "second"]) == "English"


def test_build_searchable_text_includes_title(db_schema):
    """build_searchable_text includes notice title."""
    db = SessionLocal()
    try:
        notice = Notice(
            id="test-1",
            source="TED_EU",
            source_id="TED-001",
            publication_workspace_id="ws-TED-001",
            title="Solar Panel Installation",
            url="https://example.com/1",
        )
        db.add(notice)
        db.commit()
        
        searchable = build_searchable_text(notice)
        assert "solar panel installation" in searchable.lower()
    finally:
        db.close()


def test_build_searchable_text_includes_raw_data_fields(db_schema):
    """build_searchable_text extracts fields from raw_data."""
    db = SessionLocal()
    try:
        raw = {
            "notice-title": {"eng": "Wind Energy Project", "fra": "Projet d'énergie éolienne"},
            "description-glo": "Large scale wind farm development",
        }
        notice = Notice(
            id="test-2",
            source="TED_EU",
            source_id="TED-002",
            publication_workspace_id="ws-TED-002",
            title="Untitled",
            url="https://example.com/2",
            raw_data=raw,
        )
        db.add(notice)
        db.commit()
        
        searchable = build_searchable_text(notice)
        assert "wind energy project" in searchable.lower()
        assert "wind farm development" in searchable.lower()
    finally:
        db.close()


def test_build_searchable_text_includes_notice_detail(db_schema):
    """build_searchable_text includes content from notice_detail if present."""
    db = SessionLocal()
    try:
        notice = Notice(
            id="test-3",
            source="TED_EU",
            source_id="TED-003",
            publication_workspace_id="ws-TED-003",
            title="Test Notice",
            url="https://example.com/3",
        )
        db.add(notice)
        db.commit()
        
        detail_data = {
            "title-proc": {"eng": "Procurement Title"},
            "description-proc": "Detailed description here",
        }
        detail = NoticeDetail(
            notice_id=notice.id,
            source="TED_EU",
            source_id="TED-003",
            raw_json=json.dumps(detail_data),
        )
        db.add(detail)
        db.commit()
        
        searchable = build_searchable_text(notice, detail)
        assert "test notice" in searchable.lower()
        assert "procurement title" in searchable.lower()
        assert "detailed description" in searchable.lower()
    finally:
        db.close()
