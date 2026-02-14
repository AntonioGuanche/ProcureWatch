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
        with patch("app.connectors.bosa.client.search_publications", return_value=mock_data) as mock:
            items = _fetch_page("BOSA", "*", 1, 25)
            assert len(items) == 2
            mock.assert_called_once_with(term="*", page=1, page_size=25)

    def test_fetch_ted(self):
        from app.services.scheduler import _fetch_page
        mock_data = {"notices": [{"id": "a"}]}
        with patch("app.connectors.ted.client.search_ted_notices", return_value=mock_data) as mock:
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
        mock_result = {
            "status": "ok",
            "total_created": 5,
            "total_updated": 1,
            "elapsed_seconds": 2.0,
            "backfill": {"enriched": 2},
            "watchlist_matcher": {"total_new_matches": 1},
        }

        with patch.object(sched_mod, "settings") as mock_settings, \
             patch("app.db.session.SessionLocal", return_value=mock_db), \
             patch("app.services.bulk_import.bulk_import_all", return_value=mock_result) as mock_all:

            mock_settings.import_sources = "BOSA,TED"
            mock_settings.import_term = "*"
            mock_settings.import_term_ted = "*"
            mock_settings.import_ted_days_back = 7
            mock_settings.import_page_size = 25
            mock_settings.import_max_pages = 1
            mock_settings.backfill_after_import = True
            mock_settings.scheduler_enabled = True

            sched_mod._run_import_pipeline()

            mock_all.assert_called_once()
            result = sched_mod._last_run.get("import_pipeline")
            assert result is not None
            assert result["status"] == "ok"
            assert result["total_created"] == 5
            assert "watchlist_matcher" in result
            assert "backfill" in result
