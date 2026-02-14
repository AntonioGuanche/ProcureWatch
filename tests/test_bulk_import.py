"""Tests for Phase 10: bulk import service."""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


class TestFetchPages:
    """Test individual page fetch helpers."""

    def test_bosa_extracts_publications(self):
        from app.services.bulk_import import _fetch_page_bosa
        mock_resp = {
            "metadata": {"totalCount": 200},
            "json": {"publications": [{"id": "1"}, {"id": "2"}]},
        }
        with patch("app.connectors.bosa.client.search_publications", return_value=mock_resp):
            result = _fetch_page_bosa("*", 1, 25)
            assert len(result["items"]) == 2
            assert result["total_count"] == 200

    def test_ted_extracts_notices(self):
        from app.services.bulk_import import _fetch_page_ted
        mock_resp = {
            "metadata": {"totalCount": 500},
            "json": {"notices": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
        }
        with patch("app.connectors.ted.client.search_ted_notices", return_value=mock_resp):
            result = _fetch_page_ted("construction", 1, 50)
            assert len(result["items"]) == 3
            assert result["total_count"] == 500

    def test_bosa_empty_response(self):
        from app.services.bulk_import import _fetch_page_bosa
        mock_resp = {"metadata": {}, "json": {}}
        with patch("app.connectors.bosa.client.search_publications", return_value=mock_resp):
            result = _fetch_page_bosa("*", 1, 25)
            assert result["items"] == []

    def test_ted_total_in_json(self):
        from app.services.bulk_import import _fetch_page_ted
        mock_resp = {
            "metadata": {},
            "json": {"notices": [{"id": "x"}], "totalCount": 42},
        }
        with patch("app.connectors.ted.client.search_ted_notices", return_value=mock_resp):
            result = _fetch_page_ted("*", 1, 10)
            assert result["total_count"] == 42


class TestBulkImportSource:
    """Test single-source bulk import."""

    def test_auto_pagination_from_total_count(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()
        call_count = 0

        def mock_fetch(term, page, page_size, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return {
                    "items": [{"publicationWorkspaceId": f"ws-{call_count}-{i}"} for i in range(10)],
                    "total_count": 25,  # 25 total → 3 pages of 10
                }
            return {"items": [], "total_count": 25}

        import asyncio

        async def mock_import(items, fetch_details=False):
            return {"created": len(items), "updated": 0, "skipped": 0, "errors": []}

        mock_svc = MagicMock()
        mock_svc.import_from_eproc_search = mock_import

        with patch("app.services.bulk_import._fetch_page_bosa", side_effect=mock_fetch), \
             patch("app.services.bulk_import.NoticeService", return_value=mock_svc):
            result = bulk_import_source(db, "BOSA", page_size=10)

        assert result["total_created"] == 25
        assert result["pages_fetched"] == 3
        assert result["api_total_count"] == 25

    def test_stops_on_empty_page(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()

        def mock_fetch(term, page, page_size, **kwargs):
            if page == 1:
                return {"items": [{"publicationWorkspaceId": "ws-1"}], "total_count": None}
            return {"items": [], "total_count": None}

        import asyncio

        async def mock_import(items, fetch_details=False):
            return {"created": 1, "updated": 0, "skipped": 0, "errors": []}

        mock_svc = MagicMock()
        mock_svc.import_from_eproc_search = mock_import

        with patch("app.services.bulk_import._fetch_page_bosa", side_effect=mock_fetch), \
             patch("app.services.bulk_import.NoticeService", return_value=mock_svc):
            result = bulk_import_source(db, "BOSA", page_size=50)

        assert result["pages_fetched"] == 1
        assert result["total_created"] == 1

    def test_stops_on_partial_page(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()

        def mock_fetch(term, page, page_size, **kwargs):
            # Return fewer items than page_size → last page
            return {
                "items": [{"publicationWorkspaceId": f"ws-{i}"} for i in range(3)],
                "total_count": 3,
            }

        import asyncio

        async def mock_import(items, fetch_details=False):
            return {"created": len(items), "updated": 0, "skipped": 0, "errors": []}

        mock_svc = MagicMock()
        mock_svc.import_from_eproc_search = mock_import

        with patch("app.services.bulk_import._fetch_page_bosa", side_effect=mock_fetch), \
             patch("app.services.bulk_import.NoticeService", return_value=mock_svc):
            result = bulk_import_source(db, "BOSA", page_size=50)

        assert result["pages_fetched"] == 1

    def test_respects_max_pages(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()
        pages_called = []

        def mock_fetch(term, page, page_size, **kwargs):
            pages_called.append(page)
            return {
                "items": [{"publicationWorkspaceId": f"ws-{page}-{i}"} for i in range(50)],
                "total_count": 10000,  # Would need 200 pages
            }

        import asyncio

        async def mock_import(items, fetch_details=False):
            return {"created": len(items), "updated": 0, "skipped": 0, "errors": []}

        mock_svc = MagicMock()
        mock_svc.import_from_eproc_search = mock_import

        with patch("app.services.bulk_import._fetch_page_bosa", side_effect=mock_fetch), \
             patch("app.services.bulk_import.NoticeService", return_value=mock_svc):
            result = bulk_import_source(db, "BOSA", page_size=50, max_pages=5)

        assert result["pages_fetched"] == 5
        assert len(pages_called) == 5

    def test_unknown_source(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()
        result = bulk_import_source(db, "UNKNOWN")
        assert "error" in result

    def test_ted_source(self):
        from app.services.bulk_import import bulk_import_source

        db = MagicMock()

        def mock_fetch(term, page, page_size, **kwargs):
            if page == 1:
                return {"items": [{"publication-number": "123-2024"}], "total_count": 1}
            return {"items": [], "total_count": 1}

        import asyncio

        async def mock_import(items, fetch_details=False):
            return {"created": 1, "updated": 0, "skipped": 0, "errors": []}

        mock_svc = MagicMock()
        mock_svc.import_from_ted_search = mock_import

        with patch("app.services.bulk_import._fetch_page_ted", side_effect=mock_fetch), \
             patch("app.services.bulk_import.NoticeService", return_value=mock_svc):
            result = bulk_import_source(db, "TED", page_size=50)

        assert result["total_created"] == 1


class TestBulkImportAll:
    """Test multi-source bulk import with pipeline."""

    def test_runs_both_sources_and_backfill(self):
        from app.services.bulk_import import bulk_import_all

        db = MagicMock()

        with patch("app.services.bulk_import.bulk_import_source") as mock_source, \
             patch("app.services.enrichment_service.backfill_from_raw_data", return_value={"enriched": 5}), \
             patch("app.services.enrichment_service.refresh_search_vectors", return_value=10), \
             patch("app.services.watchlist_matcher.run_watchlist_matcher", return_value={"total_new_matches": 2}):

            mock_source.side_effect = [
                {"total_created": 10, "total_updated": 2},  # BOSA
                {"total_created": 5, "total_updated": 0},   # TED
            ]

            result = bulk_import_all(db, sources="BOSA,TED")

        assert result["total_created"] == 15
        assert result["total_updated"] == 2
        assert "backfill" in result
        assert "watchlist_matcher" in result

    def test_skips_backfill_when_no_changes(self):
        from app.services.bulk_import import bulk_import_all

        db = MagicMock()

        with patch("app.services.bulk_import.bulk_import_source") as mock_source, \
             patch("app.services.enrichment_service.backfill_from_raw_data") as mock_bf:

            mock_source.return_value = {"total_created": 0, "total_updated": 0}
            result = bulk_import_all(db, sources="BOSA")

        mock_bf.assert_not_called()
