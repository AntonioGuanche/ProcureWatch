"""Unit tests for extract_lots and extract_documents (offline, fake payload)."""
import pytest
from connectors.eprocurement.detail_extractors import extract_documents, extract_lots


FAKE_DETAIL_WITH_LOTS = {
    "dossier": {
        "lots": [
            {
                "lotNumber": "1",
                "title": "Lot 1 - Works",
                "description": "Construction works",
                "cpvCode": {"code": "45000000"},
                "nutsCode": {"code": "BE1"},
            },
            {
                "number": "2",
                "name": "Lot 2",
            },
        ],
    },
}

FAKE_DETAIL_WITH_DOCUMENTS = {
    "dossier": {
        "documents": [
            {
                "url": "https://example.com/doc1.pdf",
                "title": "Specifications",
                "fileType": "PDF",
                "language": "FR",
            },
            {
                "link": "https://example.com/doc2.pdf",
                "fileName": "annex.pdf",
            },
        ],
    },
}

FAKE_DETAIL_EMPTY = {}


def test_extract_lots_empty():
    """extract_lots returns [] for empty or non-dict input."""
    assert extract_lots(FAKE_DETAIL_EMPTY) == []
    assert extract_lots({}) == []
    assert extract_lots(None) == []
    assert extract_lots([]) == []


def test_extract_lots_from_dossier():
    """extract_lots parses dossier.lots and returns normalized dicts."""
    result = extract_lots(FAKE_DETAIL_WITH_LOTS)
    assert len(result) == 2
    assert result[0]["lot_number"] == "1"
    assert result[0]["title"] == "Lot 1 - Works"
    assert result[0]["description"] == "Construction works"
    assert result[0]["cpv_code"] == "45000000"
    assert result[0]["nuts_code"] == "BE1"
    assert result[1]["lot_number"] == "2"
    assert result[1]["title"] == "Lot 2"


def test_extract_documents_empty():
    """extract_documents returns [] for empty or when no url."""
    assert extract_documents(FAKE_DETAIL_EMPTY) == []
    assert extract_documents({"dossier": {"documents": [{"title": "No URL"}]}}) == []


def test_extract_documents_from_dossier():
    """extract_documents parses dossier.documents and returns normalized dicts with url."""
    result = extract_documents(FAKE_DETAIL_WITH_DOCUMENTS)
    assert len(result) == 2
    assert result[0]["url"] == "https://example.com/doc1.pdf"
    assert result[0]["title"] == "Specifications"
    assert result[0]["file_type"] == "PDF"
    assert result[0]["language"] == "FR"
    assert result[1]["url"] == "https://example.com/doc2.pdf"
    assert result[1]["title"] == "annex.pdf"
