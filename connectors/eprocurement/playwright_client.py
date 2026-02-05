"""Playwright-based e-Procurement client (wraps existing Node.js collector)."""
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Project root (parent of connectors)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
COLLECTOR_SCRIPT = SCRIPTS_DIR / "collect_publicprocurement.js"
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "publicprocurement"


class PlaywrightCollectorError(Exception):
    """Raised when the Playwright collector fails."""

    pass


class PlaywrightEProcurementClient:
    """
    Wraps the existing Node.js Playwright collector.
    Exposes the same interface as OfficialEProcurementClient.
    Runs the collector script and reads the saved JSON file.
    """

    def __init__(
        self,
        collector_script: Optional[Path] = None,
        data_dir: Optional[Path] = None,
        timeout_seconds: int = 180,
    ):
        self.collector_script = collector_script or COLLECTOR_SCRIPT
        self.data_dir = data_dir or DATA_DIR
        self.timeout_seconds = timeout_seconds
        self._last_output_file: Optional[Path] = None

    def _run_collector(self, term: str, page: int, page_size: int) -> Path:
        """
        Run the Node.js collector script. Returns path to the created JSON file.
        """
        if not self.collector_script.exists():
            raise PlaywrightCollectorError(
                f"Collector script not found: {self.collector_script}"
            )

        # List existing files before run
        self.data_dir.mkdir(parents=True, exist_ok=True)
        files_before = set(self.data_dir.glob("publicprocurement_*.json"))

        result = subprocess.run(
            ["node", str(self.collector_script), term, str(page), str(page_size)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

        if result.returncode != 0:
            err = result.stderr or result.stdout or "Unknown error"
            raise PlaywrightCollectorError(
                f"Collector failed with exit code {result.returncode}: {err[:500]}"
            )

        files_after = set(self.data_dir.glob("publicprocurement_*.json"))
        new_files = files_after - files_before

        if not new_files:
            # Use newest file if no new file was created (e.g. already run)
            all_files = list(self.data_dir.glob("publicprocurement_*.json"))
            if not all_files:
                raise PlaywrightCollectorError(
                    "Collector completed but no JSON file was produced."
                )
            newest = max(all_files, key=lambda p: p.stat().st_mtime)
            self._last_output_file = newest
            return newest

        # Newest among new files
        newest = max(new_files, key=lambda p: p.stat().st_mtime)
        self._last_output_file = newest
        return newest

    def _read_saved_output(self, file_path: Path) -> dict[str, Any]:
        """Read and return the collector output structure."""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def search_publications(
        self,
        term: str,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        """
        Run Playwright collector and return result in standard format:
        {"metadata": {...}, "json": {...}}
        """
        file_path = self._run_collector(term, page, page_size)
        data = self._read_saved_output(file_path)

        # Normalize to standard shape if needed
        if "metadata" in data and "json" in data:
            return data
        # If collector wrote raw API response
        if "publications" in data:
            metadata = {
                "term": term,
                "page": page,
                "pageSize": page_size,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "playwright",
            }
            return {"metadata": metadata, "json": data}
        return {"metadata": {}, "json": data}

    def get_publication_detail(self, publication_id: str) -> Optional[dict[str, Any]]:
        """
        Playwright collector does not implement single publication fetch.
        Return None; callers can use search result data instead.
        """
        logger.warning(
            "Playwright client does not support get_publication_detail; publication_id=%s",
            publication_id,
        )
        return None

    def get_cpv_label(self, code: str, lang: str = "fr") -> Optional[str]:
        """
        Playwright collector does not implement CPV label lookup.
        Return None.
        """
        logger.warning(
            "Playwright client does not support get_cpv_label; code=%s lang=%s",
            code,
            lang,
        )
        return None
