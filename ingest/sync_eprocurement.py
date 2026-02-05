#!/usr/bin/env python3
"""
Robust sync run: search (provider=auto by default), save raw JSON, import via
ingest/import_publicprocurement.py (subprocess), emit machine-readable summary.
Idempotent: re-running for same term updates last_seen_at, does not duplicate.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "raw" / "publicprocurement"


def run_search(term: str, page: int, page_size: int, provider: str | None) -> dict:
    """Run search via connectors; returns result dict (metadata + json)."""
    if provider is not None:
        os.environ["EPROC_MODE"] = provider
    from connectors.eprocurement.client import search_publications

    return search_publications(term=term, page=page, page_size=page_size)


def save_raw(result: dict, out_path: Path) -> int:
    """Save result to JSON file; return count of publications (fetched)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    data = result.get("json", result)
    publications = data.get("publications") or data.get("items") or data.get("results") or []
    return len(publications) if isinstance(publications, list) else 0


def run_import(file_path: Path) -> tuple[int, int, int]:
    """
    Run ingest/import_publicprocurement.py as subprocess; parse stdout for
    imported_new, imported_updated, errors. Returns (imported_new, imported_updated, errors).
    """
    cmd = [sys.executable, str(PROJECT_ROOT / "ingest" / "import_publicprocurement.py"), str(file_path)]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    full_output = stdout + "\n" + stderr

    # "Import complete: X created, Y updated"
    match = re.search(r"Import complete:\s*(\d+)\s+created,\s*(\d+)\s+updated", full_output)
    created = int(match.group(1)) if match else 0
    updated = int(match.group(2)) if match else 0

    # Count integrity/import errors (lines with "Integrity error" or "✗")
    errors = len(re.findall(r"Integrity error|✗.*error", full_output, re.IGNORECASE))

    return created, updated, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync e-Procurement: search, save raw JSON, import (idempotent), emit summary.",
    )
    parser.add_argument("--term", default="travaux", help="Search term")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--page-size", type=int, default=25, help="Page size")
    parser.add_argument(
        "--provider",
        choices=("official", "playwright", "auto"),
        default=None,
        help="Override EPROC_MODE (default: auto)",
    )
    args = parser.parse_args()

    # 1) Run search
    try:
        result = run_search(args.term, args.page, args.page_size, args.provider)
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        return 1

    # 2) Save raw JSON
    now = datetime.utcnow()
    ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
    filename = f"publicprocurement_{ts}.json"
    out_path = DATA_DIR / filename
    fetched = save_raw(result, out_path)
    print(f"Saved: {out_path} ({fetched} publications)")

    # 3) Import via existing script (subprocess)
    imported_new, imported_updated, errors = run_import(out_path)

    # 4) Machine-readable summary
    summary = {
        "fetched": fetched,
        "imported_new": imported_new,
        "imported_updated": imported_updated,
        "errors": errors,
    }
    print(json.dumps(summary))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
