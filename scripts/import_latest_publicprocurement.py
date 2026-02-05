#!/usr/bin/env python3
"""Import the newest collected publicprocurement JSON file into the database."""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "publicprocurement"


def main() -> int:
    if not DATA_DIR.exists():
        print(f"No data directory: {DATA_DIR}", file=sys.stderr)
        return 1

    # Newest file matching publicprocurement_*.json (exclude _debug folder)
    files = [f for f in DATA_DIR.glob("publicprocurement_*.json") if f.is_file()]
    if not files:
        print("No file found matching data/raw/publicprocurement/publicprocurement_*.json", file=sys.stderr)
        return 1

    latest = max(files, key=lambda p: p.stat().st_mtime)
    importer = PROJECT_ROOT / "ingest" / "import_publicprocurement.py"
    if not importer.exists():
        print(f"Importer not found: {importer}", file=sys.stderr)
        return 1

    result = subprocess.run(
        [sys.executable, str(importer), str(latest)],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        return result.returncode
    print(f"Imported: {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
