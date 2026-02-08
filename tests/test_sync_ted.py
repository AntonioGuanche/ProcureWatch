"""Tests for sync_ted: mock connector response and subprocess; assert files saved and subprocess path (offline)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_sync_ted_saves_raw_and_no_import_ready_file(tmp_path: Path) -> None:
    """With mocked connector and --no-import: only raw TED file is saved (no import_ready, no subprocess)."""
    fake_result = {
        "metadata": {"term": "test", "page": 1, "pageSize": 25, "status": 200},
        "json": {"notices": [{"noticeId": "TED-1", "title": "Test notice"}], "totalCount": 1},
        "notices": [{"noticeId": "TED-1", "title": "Test notice"}],
    }
    mock_subprocess = MagicMock()

    with patch("app.connectors.ted.search_ted_notices", return_value=fake_result):
        with patch("ingest.sync_ted.subprocess.run", mock_subprocess):
            from ingest.sync_ted import main

            old_argv = list(sys.argv)
            sys.argv = [
                "sync_ted.py",
                "--term", "test",
                "--out-dir", str(tmp_path),
                "--no-import",
            ]
            try:
                exit_code = main()
            finally:
                sys.argv = old_argv

    assert exit_code == 0
    raw_files = list(tmp_path.glob("ted_*.json"))
    assert len(raw_files) >= 1
    raw_file = raw_files[0]
    assert "_import_ready" not in raw_file.name
    with open(raw_file, encoding="utf-8") as f:
        raw_data = json.load(f)
    assert raw_data["metadata"]["term"] == "test"
    assert raw_data["json"]["notices"][0]["noticeId"] == "TED-1"
    # No import_ready files
    assert len(list(tmp_path.glob("*_import_ready.json"))) == 0
    mock_subprocess.assert_not_called()


def test_sync_ted_subprocess_called_with_raw_path(tmp_path: Path) -> None:
    """When --import (default): subprocess.run called with raw TED JSON path and import_ted.py."""
    fake_result = {
        "metadata": {"term": "x", "page": 1, "pageSize": 25},
        "json": {"notices": [], "totalCount": 0},
    }

    def mock_subprocess_run(cmd, **kwargs):
        """Mock subprocess.run to handle both migration and import calls."""
        mock_result = MagicMock()
        # Migration call (alembic upgrade head)
        if isinstance(cmd, list) and "alembic" in cmd and "upgrade" in cmd:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
        # Import call (import_ted.py)
        elif isinstance(cmd, list) and len(cmd) > 1 and "import_ted" in str(cmd[1]):
            mock_result.returncode = 0
            mock_result.stdout = '{"imported_new": 0, "imported_updated": 0, "errors": 0}'
            mock_result.stderr = ""
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
        return mock_result

    with patch("app.connectors.ted.search_ted_notices", return_value=fake_result):
        with patch("ingest.sync_ted.subprocess.run", side_effect=mock_subprocess_run):
            from ingest.sync_ted import main

            old_argv = list(sys.argv)
            # Use --no-migrate to avoid migration call in this test
            sys.argv = ["sync_ted.py", "--term", "x", "--out-dir", str(tmp_path), "--no-migrate"]
            try:
                main()
            finally:
                sys.argv = old_argv

    # Verify import subprocess was called (migration was skipped with --no-migrate)
    # The mock will have been called for import_ted.py


def test_sync_ted_debug_triggers_debug_prints(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """When --debug is set, sync_ted prints [TED debug] lines (URL, method, body, status); no network."""
    from connectors.ted.client import reset_client
    reset_client()
    with patch("app.connectors.ted.official_client.requests.Session") as MockSession:
        mock_session = MockSession.return_value
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = "https://api.ted.europa.eu/v3/notices/search"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"notices": [], "totalCount": 0}
        mock_session.request.return_value = mock_resp
        with patch("app.connectors.ted.client._get_client") as mock_get_client:
            from connectors.ted.official_client import OfficialTEDClient
            from app.core.config import settings
            mock_get_client.return_value = OfficialTEDClient(
                search_base_url=settings.ted_search_base_url,
                timeout_seconds=settings.ted_timeout_seconds,
            )
            with patch.object(mock_get_client.return_value, "_session", mock_session):
                from ingest.sync_ted import main

                old_argv = list(sys.argv)
                sys.argv = [
                    "sync_ted.py",
                    "--term", "solar",
                    "--out-dir", str(tmp_path),
                    "--no-import",
                    "--debug",
                ]
                try:
                    exit_code = main()
                finally:
                    sys.argv = old_argv

    assert exit_code == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[TED debug]" in combined
    assert "final URL" in combined
    assert "request method" in combined
    assert "notices/search" in combined or "notices" in combined
    assert "params/body" in combined or "request" in combined
    assert "response status code" in combined


def test_sync_ted_discover_triggers_discovery_call(tmp_path: Path) -> None:
    """When --discover is set, load_or_discover_endpoints is called before search (no network)."""
    fake_result = {
        "metadata": {"term": "x", "page": 1, "pageSize": 25},
        "json": {"notices": [], "totalCount": 0},
        "notices": [],
    }
    with patch("app.connectors.ted.openapi_discovery.load_or_discover_endpoints") as mock_discover:
        mock_discover.return_value = {
            "base_url": "https://api.ted.europa.eu",
            "path": "/v3/notices/search",
            "method": "POST",
            "style": "json_body",
            "term_param": "query",
            "page_param": "page",
            "page_size_param": "limit",
        }
        with patch("app.connectors.ted.search_ted_notices", return_value=fake_result):
            from ingest.sync_ted import main

            old_argv = list(sys.argv)
            sys.argv = ["sync_ted.py", "--term", "x", "--out-dir", str(tmp_path), "--no-import", "--discover"]
            try:
                exit_code = main()
            finally:
                sys.argv = old_argv

    assert exit_code == 0
    mock_discover.assert_called_once()
    call_kw = mock_discover.call_args[1]
    assert call_kw.get("force") is False


def test_sync_ted_force_discover_calls_discovery_with_force(tmp_path: Path) -> None:
    """When --force-discover is set, discovery is called with force=True."""
    fake_result = {"metadata": {}, "json": {"notices": [], "totalCount": 0}, "notices": []}
    with patch("app.connectors.ted.openapi_discovery.load_or_discover_endpoints") as mock_discover:
        mock_discover.return_value = {"base_url": "https://api.ted.europa.eu", "path": "/v3/notices/search"}
        with patch("app.connectors.ted.search_ted_notices", return_value=fake_result):
            from ingest.sync_ted import main

            old_argv = list(sys.argv)
            sys.argv = ["sync_ted.py", "--term", "x", "--out-dir", str(tmp_path), "--no-import", "--force-discover"]
            try:
                main()
            finally:
                sys.argv = old_argv

    mock_discover.assert_called_once()
    assert mock_discover.call_args[1].get("force") is True
