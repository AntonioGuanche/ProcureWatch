#!/usr/bin/env python3
"""Railway cron entry point for daily procurement import.

Usage (Railway cron service):
    python scripts/cron_import.py

Environment variables (all optional, with defaults):
    IMPORT_SOURCES      Comma-separated: BOSA,TED (default: BOSA,TED)
    IMPORT_TERM         Search term (default: *)
    IMPORT_DAYS_BACK    Days to look back (default: 3)
    IMPORT_PAGE_SIZE    Results per page (default: 100)
    IMPORT_MAX_PAGES    Max pages per source (default: 10)
    IMPORT_ALERT_EMAIL  Email for high error rate alerts

Railway cron setup:
    1. Create a new service in Railway (same repo)
    2. Set start command: python scripts/cron_import.py
    3. Set schedule: 0 6 * * * (daily at 06:00 UTC)
    4. Attach the same Postgres database
    5. Copy env vars from web service
"""
import os
import sys
from pathlib import Path

# Project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    # Run migrations first (idempotent)
    print("Running alembic upgrade head...")
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        print("WARNING: alembic upgrade failed, continuing anyway")

    # Build argv for import_daily
    sources = os.environ.get("IMPORT_SOURCES", "BOSA,TED")
    term = os.environ.get("IMPORT_TERM", "*")
    days_back = os.environ.get("IMPORT_DAYS_BACK", "3")
    page_size = os.environ.get("IMPORT_PAGE_SIZE", "100")
    max_pages = os.environ.get("IMPORT_MAX_PAGES", "10")

    sys.argv = [
        "import_daily.py",
        "--sources", sources,
        "--term", term,
        "--days-back", days_back,
        "--page-size", page_size,
        "--max-pages", max_pages,
        "--log-file", "logs/cron_import.log",
    ]

    from scripts.import_daily import main as import_main
    return import_main()


if __name__ == "__main__":
    sys.exit(main())
