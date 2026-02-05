#!/usr/bin/env python3
"""
Sync TED (EU Tenders Electronic Daily): search via official API, save raw JSON,
optionally run import_ted.py (subprocess). Emits machine-readable JSON summary:
fetched, imported_new, imported_updated, errors, saved_path.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "raw" / "ted"


def _count_fetched(result: dict) -> int:
    """Count notices in TED result json (notices, results, items, or data)."""
    raw = result.get("json", result)
    notices = (
        raw.get("notices")
        or raw.get("results")
        or raw.get("items")
        or raw.get("data")
        or []
    )
    return len(notices) if isinstance(notices, list) else 0


def run_import(file_path: Path) -> tuple[int, int, int]:
    """
    Run ingest/import_ted.py as subprocess; parse stdout for JSON summary
    (imported_new, imported_updated, errors). Returns (imported_new, imported_updated, errors).
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "ingest" / "import_ted.py"),
        str(file_path),
    ]
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

    # Parse JSON summary line (last line with imported_new)
    created, updated, errors = 0, 0, 0
    for line in reversed(full_output.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            summary = json.loads(line)
            if "imported_new" in summary:
                created = int(summary.get("imported_new", 0))
                updated = int(summary.get("imported_updated", 0))
                errors = int(summary.get("errors", 0))
                break
        except json.JSONDecodeError:
            continue
    return created, updated, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync TED: search, save raw JSON, optionally import via import_ted.py.",
    )
    parser.add_argument("--term", default="construction", help="Search term")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--page-size", type=int, default=25, help="Page size")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for raw TED JSON (default: data/raw/ted)",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        default=True,
        help="Run import after fetch (default: true)",
    )
    parser.add_argument(
        "--no-import",
        dest="do_import",
        action="store_false",
        help="Skip import step",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print TED request URL, body, response status/headers/body (on non-2xx) for diagnostics",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Run OpenAPI discovery before search (fetch spec and cache endpoint descriptor)",
    )
    parser.add_argument(
        "--force-discover",
        action="store_true",
        help="Force discovery and overwrite cached TED endpoints, then run search",
    )
    args = parser.parse_args()

    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 0) Optional: run discovery first
    if args.discover or args.force_discover:
        try:
            from connectors.ted.openapi_discovery import TEDDiscoveryError, load_or_discover_endpoints
            from app.core.config import settings
            load_or_discover_endpoints(
                force=args.force_discover,
                host=settings.ted_search_base_url or None,
                timeout=settings.ted_timeout_seconds,
            )
        except TEDDiscoveryError as e:
            print(f"TED discovery failed: {e}", file=sys.stderr)
            print(
                "Hint: Ensure TED_SEARCH_BASE_URL points to the API host (e.g. https://ted.europa.eu) and the host serves an OpenAPI spec.",
                file=sys.stderr,
            )
            return 1
        except Exception as e:
            print(f"TED discovery failed: {e}", file=sys.stderr)
            return 1

    # 1) Search TED
    try:
        from connectors.ted import search_ted_notices

        result = search_ted_notices(
            term=args.term,
            page=args.page,
            page_size=args.page_size,
            debug=args.debug,
        )
    except Exception as e:
        print(f"TED search failed: {e}", file=sys.stderr)
        return 1

    fetched = _count_fetched(result)

    # 2) Save raw JSON
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
    raw_filename = f"ted_{ts}.json"
    saved_path = out_dir / raw_filename
    with open(saved_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved raw: {saved_path} ({fetched} notices)")

    imported_new, imported_updated, errors = 0, 0, 0
    if args.do_import:
        imported_new, imported_updated, errors = run_import(saved_path)

    # 4) JSON summary
    summary = {
        "fetched": fetched,
        "imported_new": imported_new,
        "imported_updated": imported_updated,
        "errors": errors,
        "saved_path": str(saved_path),
    }
    print(json.dumps(summary))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
