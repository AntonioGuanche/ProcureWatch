#!/usr/bin/env python3
"""
Convenience wrapper to run the BOSA sync pipeline from the project root.

Usage:
    python scripts/sync_bosa.py --query "travaux" --limit 25 --import
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present (before any imports that need env vars)
from app.utils.env import load_env_if_present
load_env_if_present()

from ingest.sync_bosa import main as sync_bosa_main


def main() -> int:
    """Delegate to ingest.sync_bosa.main()."""
    return sync_bosa_main()


if __name__ == "__main__":
    raise SystemExit(main())
