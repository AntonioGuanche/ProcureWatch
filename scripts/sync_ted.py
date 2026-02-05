#!/usr/bin/env python3
"""
Convenience wrapper to run the TED sync pipeline from the project root.

Usage:
    python scripts/sync_ted.py --query "forest restoration" --limit 25 --import
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingest.sync_ted import main as sync_ted_main


def main() -> int:
    """Delegate to ingest.sync_ted.main()."""
    return sync_ted_main()


if __name__ == "__main__":
    raise SystemExit(main())

