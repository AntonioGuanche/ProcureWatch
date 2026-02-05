#!/usr/bin/env python3
"""Daily pipeline orchestrator for procurement data collection and ingestion."""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging

# Setup logging
setup_logging()

# Constants
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "publicprocurement"
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "daily_pipeline.log"

# Collector script paths
COLLECTOR_SCRIPT = SCRIPT_DIR / "collect_publicprocurement.js"
INGEST_SCRIPT = PROJECT_ROOT / "ingest" / "import_publicprocurement.py"


class PipelineLogger:
    """Logger that writes to both stdout and log file."""

    def __init__(self, log_file: Path):
        """Initialize logger with log file path."""
        self.log_file = log_file
        self.ensure_log_dir()

    def ensure_log_dir(self) -> None:
        """Ensure log directory exists."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message to both stdout and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"
        
        # Print to stdout
        print(formatted_message)
        
        # Append to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(formatted_message + "\n")
        except Exception as e:
            print(f"Warning: Failed to write to log file: {e}", file=sys.stderr)


def find_newest_json_file(directory: Path) -> Optional[Path]:
    """
    Find the newest JSON file in the directory.
    Uses filesystem mtime as primary method, filename timestamp as fallback.
    """
    if not directory.exists():
        return None
    
    json_files = list(directory.glob("publicprocurement_*.json"))
    
    if not json_files:
        return None
    
    # Sort by mtime (most recent first)
    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return json_files[0]


def get_file_timestamp_from_name(filepath: Path) -> Optional[datetime]:
    """Extract timestamp from filename if possible."""
    # Pattern: publicprocurement_2026-01-29T05-33-05-566Z.json
    match = re.search(r"publicprocurement_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)", filepath.name)
    if match:
        try:
            timestamp_str = match.group(1).replace("-", ":")
            # Replace last colon with dot for milliseconds
            timestamp_str = timestamp_str.rsplit(":", 1)[0] + "." + timestamp_str.rsplit(":", 1)[1]
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            pass
    return None


def run_collector(logger: PipelineLogger, term: str = "travaux", page: int = 1, page_size: int = 25) -> Tuple[bool, Optional[str]]:
    """
    Run the Node.js collector script.
    Returns (success, error_message).
    """
    logger.log(f"Starting collection: term={term}, page={page}, pageSize={page_size}")
    
    if not COLLECTOR_SCRIPT.exists():
        error_msg = f"Collector script not found: {COLLECTOR_SCRIPT}"
        logger.log(error_msg, "ERROR")
        return False, error_msg
    
    try:
        # Get list of files before collection
        files_before = set(DATA_DIR.glob("publicprocurement_*.json")) if DATA_DIR.exists() else set()
        
        # Run collector
        result = subprocess.run(
            ["node", str(COLLECTOR_SCRIPT), term, str(page), str(page_size)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes timeout
        )
        
        # Check for new files
        files_after = set(DATA_DIR.glob("publicprocurement_*.json")) if DATA_DIR.exists() else set()
        new_files = files_after - files_before
        
        if result.returncode != 0:
            error_msg = f"Collection failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nStderr: {result.stderr[:500]}"
            logger.log(error_msg, "ERROR")
            return False, error_msg
        
        if not new_files:
            logger.log("Collection completed but no new file was created (may have been cancelled or already run)", "WARNING")
            # Still return success - we'll check for newest existing file
            return True, None
        
        # Log collector output
        if result.stdout:
            logger.log(f"Collector output: {result.stdout[:500]}")
        
        newest_file = find_newest_json_file(DATA_DIR)
        if newest_file and newest_file in new_files:
            logger.log(f"Collection successful: {newest_file.name}")
            return True, None
        else:
            logger.log("Collection completed but could not identify new file", "WARNING")
            return True, None
            
    except subprocess.TimeoutExpired:
        error_msg = "Collection timed out after 3 minutes"
        logger.log(error_msg, "ERROR")
        return False, error_msg
    except Exception as e:
        error_msg = f"Collection failed with exception: {str(e)}"
        logger.log(error_msg, "ERROR")
        return False, error_msg


def run_import(logger: PipelineLogger, json_file: Path) -> Tuple[bool, int, int]:
    """
    Run the Python ingestion script.
    Returns (success, created_count, updated_count).
    """
    logger.log(f"Starting import: {json_file.name}")
    
    if not INGEST_SCRIPT.exists():
        error_msg = f"Ingestion script not found: {INGEST_SCRIPT}"
        logger.log(error_msg, "ERROR")
        return False, 0, 0
    
    if not json_file.exists():
        error_msg = f"JSON file not found: {json_file}"
        logger.log(error_msg, "ERROR")
        return False, 0, 0
    
    try:
        result = subprocess.run(
            [sys.executable, str(INGEST_SCRIPT), str(json_file)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )
        
        # Parse output for statistics
        created_count = 0
        updated_count = 0
        
        if result.returncode != 0:
            error_msg = f"Import failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nStderr: {result.stderr[:500]}"
            logger.log(error_msg, "ERROR")
            return False, 0, 0
        
        # Parse stdout for statistics
        stdout_lines = result.stdout.split("\n")
        for line in stdout_lines:
            # Look for: "✅ Import complete: X created, Y updated"
            match = re.search(r"Import complete:\s*(\d+)\s+created,\s*(\d+)\s+updated", line)
            if match:
                created_count = int(match.group(1))
                updated_count = int(match.group(2))
                break
        
        # Log import output
        if result.stdout:
            logger.log(f"Ingestion output:\n{result.stdout[:1000]}")
        
        logger.log(f"Import successful: {created_count} created, {updated_count} updated")
        return True, created_count, updated_count
        
    except subprocess.TimeoutExpired:
        error_msg = "Import timed out after 5 minutes"
        logger.log(error_msg, "ERROR")
        return False, 0, 0
    except Exception as e:
        error_msg = f"Import failed with exception: {str(e)}"
        logger.log(error_msg, "ERROR")
        return False, 0, 0


def main() -> int:
    """Main pipeline execution."""
    logger = PipelineLogger(LOG_FILE)
    
    logger.log("=" * 60)
    logger.log("Starting daily procurement pipeline")
    logger.log("=" * 60)
    
    # Step 1: Run collector
    collection_success, collection_error = run_collector(logger)
    
    if not collection_success:
        logger.log("Pipeline failed at collection step", "ERROR")
        logger.log("=" * 60)
        return 1
    
    # Step 2: Find newest file
    newest_file = find_newest_json_file(DATA_DIR)
    
    if not newest_file:
        logger.log("No JSON files found in data directory", "WARNING")
        logger.log("Pipeline completed (no files to import)", "INFO")
        logger.log("=" * 60)
        return 0
    
    logger.log(f"Found newest file: {newest_file.name}")
    
    # Step 3: Run import
    import_success, created_count, updated_count = run_import(logger, newest_file)
    
    if not import_success:
        logger.log("Pipeline failed at import step", "ERROR")
        logger.log("=" * 60)
        return 1
    
    # Step 4: Print summary
    logger.log("=" * 60)
    logger.log("Pipeline Summary:")
    logger.log(f"  Collection Status: {'SUCCESS' if collection_success else 'FAILED'}")
    logger.log(f"  Imported File: {newest_file.name}")
    logger.log(f"  Notices Imported (new): {created_count}")
    logger.log(f"  Notices Updated (existing): {updated_count}")
    logger.log("=" * 60)
    logger.log("Pipeline completed successfully")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
