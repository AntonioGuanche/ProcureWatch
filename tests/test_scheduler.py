"""Tests for Phase 9: scheduler service."""
import os
from unittest.mock import patch, MagicMock

import pytest


class TestSchedulerConfig:
    """Test scheduler configuration and status."""

    def test_scheduler_disabled_by_default(self):
        from app.core.config import Settings
        s = Settings(database_url="sqlite:///./test.db")
        assert s.scheduler_enabled is False

    def test_scheduler_enabled_from_env(self):
        from app.core.config import Settings
        with patch.dict(os.environ, {"SCHEDULER_ENABLED": "true"}):
            s = Settings(database_url="sqlite:///./test.db")
            assert s.scheduler_enabled is True

    def test_import_interval_default(self):
        from app.core.config import Settings
        s = Settings(database_url="sqlite:///./test.db")
        assert s.import_interval_minutes == 360

    def test_import_interval_custom(self):
        from app.core.config import Settings
        with patch.dict(os.environ, {"IMPORT_INTERVAL_MINUTES": "60"}):
            s = Settings(database_url="sqlite:///./test.db")
            assert s.import_interval_minutes == 60

    def test_import_sources_default(self):
        from app.core.config import Settings
        s = Settings(database_url="sqlite:///./test.db")
        assert s.import_sources == "BOSA,TED"


class TestSchedulerStatus:
    """Test scheduler status reporting."""

    def test_status_when_disabled(self):
        with patch("app.services.scheduler.settings") as mock_settings:
            mock_settings.scheduler_enabled = False
            from app.services.scheduler import get_scheduler_status
            status = get_scheduler_status()
            assert status["enabled"] is False
            assert "SCHEDULER_ENABLED" in status["message"]

    def test_status_when_enabled_not_started(self):
        import app.services.scheduler as sched_mod
        orig_scheduler = sched_mod._scheduler
        sched_mod._scheduler = None
        try:
            with patch.object(sched_mod, "settings") as mock_settings:
                mock_settings.scheduler_enabled = True
                mock_settings.import_interval_minutes = 120
                mock_settings.import_sources = "BOSA"
                mock_settings.import_term = "*"
                mock_settings.import_page_size = 25
                mock_settings.import_max_pages = 2
                mock_settings.backfill_after_import = True
                status = sched_mod.get_scheduler_status()
                assert status["enabled"] is True
                assert status["running"] is False
                assert status["config"]["import_interval_minutes"] == 120
        finally:
            sched_mod._scheduler = orig_scheduler


class TestSchedulerLifecycle:
    """Test scheduler start/stop."""

    def test_start_when_disabled(self):
        with patch("app.services.scheduler.settings") as mock_settings:
            mock_settings.scheduler_enabled = False
            from app.services.scheduler import start_scheduler
            result = start_scheduler()
            assert result is None

    def test_start_and_stop(self):
        import app.services.scheduler as sched_mod
        orig = sched_mod._scheduler
        try:
            with patch.object(sched_mod, "settings") as mock_settings:
                mock_settings.scheduler_enabled = True
                mock_settings.import_interval_minutes = 60
                mock_settings.import_sources = "BOSA"
                mock_settings.import_term = "*"
                mock_settings.import_page_size = 25
                mock_settings.import_max_pages = 1
                mock_settings.backfill_after_import = False

                scheduler = sched_mod.start_scheduler()
                assert scheduler is not None
                assert scheduler.running is True

                jobs = scheduler.get_jobs()
                assert len(jobs) == 1
                assert jobs[0].id == "import_pipeline"

                sched_mod.stop_scheduler()
                assert sched_mod._scheduler is None
        finally:
            sched_mod._scheduler = orig


class TestFetchPage:
    """Test _fetch_page helper."""

    def test_fetch_bosa(self):
        from app.services.scheduler import _fetch_page
        mock_data = {"publications": [{"id": "1"}, {"id": "2"}]}
        with patch("app.services.scheduler.search_publications", return_value=mock_data) as mock:
            items = _fetch_page("BOSA", "*", 1, 25)
            assert len(items) == 2
            mock.assert_called_once_with(term="*", page=1, page_size=25)

    def test_fetch_ted(self):
        from app.services.scheduler import _fetch_page
        mock_data = {"notices": [{"id": "a"}]}
        with patch("app.services.scheduler.search_ted_notices", return_value=mock_data) as mock:
            items = _fetch_page("TED", "construction", 1, 10)
            assert len(items) == 1
            mock.assert_called_once_with(term="construction", page=1, page_size=10)

    def test_fetch_unknown_source(self):
        from app.services.scheduler import _fetch_page
        items = _fetch_page("UNKNOWN", "*", 1, 25)
        assert items == []


class TestImportPipeline:
    """Test the full import pipeline function."""

    def test_pipeline_runs_all_stages(self):
        import app.services.scheduler as sched_mod

        mock_db = MagicMock()
        mock_svc_instance = MagicMock()

        # Mock async import methods
        import asyncio

        async def mock_eproc(*a, **kw):
            return {"created": 3, "updated": 1, "skipped": 0, "errors": []}

        async def mock_ted(*a, **kw):
            return {"created": 2, "updated": 0, "skipped": 0, "errors": []}

        mock_svc_instance.import_from_eproc_search = mock_eproc
        mock_svc_instance.import_from_ted_search = mock_ted

        with patch.object(sched_mod, "settings") as mock_settings, \
             patch("app.services.scheduler.SessionLocal", return_value=mock_db), \
             patch("app.services.scheduler.NoticeService", return_value=mock_svc_instance), \
             patch.object(sched_mod, "_fetch_page") as mock_fetch, \
             patch("app.services.scheduler.run_watchlist_matcher", return_value={"total_new_matches": 1, "watchlists_processed": 1, "emails_sent": 0}) as mock_matcher, \
             patch("app.services.scheduler.backfill_from_raw_data", return_value={"enriched": 2}) as mock_bf, \
             patch("app.services.scheduler.refresh_search_vectors", return_value=5):

            mock_settings.import_sources = "BOSA,TED"
            mock_settings.import_term = "*"
            mock_settings.import_page_size = 25
            mock_settings.import_max_pages = 1
            mock_settings.backfill_after_import = True

            # Each source returns 1 page of items then empty
            mock_fetch.side_effect = [
                [{"id": "1"}],  # BOSA page 1
                [{"id": "a"}],  # TED page 1
            ]

            sched_mod._run_import_pipeline()

            result = sched_mod._last_run.get("import_pipeline")
            assert result is not None
            assert result["status"] == "ok"
            assert result["total_created"] == 5
            assert "watchlist_matcher" in result
            assert "backfill" in result
