#!/usr/bin/env python3
"""
Sync BOSA e-Procurement: search via official API (OAuth2), save raw JSON to data/raw/bosa,
optionally run import_bosa (subprocess) when --import is passed.
Emits machine-readable JSON summary: fetched, imported_new, imported_updated, errors, saved_path.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present (before any imports that need env vars)
from app.utils.env import load_env_if_present
load_env_if_present()

DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "raw" / "bosa"


def _endpoints_confirmed() -> bool:
    """Check if endpoints cache exists and is confirmed."""
    try:
        from app.connectors.bosa.openapi_discovery import cache_path
        import json
        cache_file = cache_path()
        if not cache_file.exists():
            return False
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("confirmed", False)
    except Exception:
        return False


def _count_fetched(result: dict) -> int:
    """Count publications in BOSA result json (publications, items, results, data)."""
    raw = result.get("json", result)
    items = (
        raw.get("publications")
        or raw.get("items")
        or raw.get("results")
        or raw.get("data")
        or []
    )
    return len(items) if isinstance(items, list) else 0


def ensure_db_migrated(db_url: str) -> None:
    """Run Alembic migrations for the given DATABASE_URL. Raises RuntimeError on failure."""
    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if proc.returncode != 0:
        error_msg = f"Database migration failed (exit code {proc.returncode})"
        if proc.stderr:
            error_msg += f"\nStderr: {proc.stderr}"
        if proc.stdout:
            error_msg += f"\nStdout: {proc.stdout}"
        raise RuntimeError(error_msg)


def run_import(file_path: Path, db_url: str) -> tuple[int, int, int]:
    """Run ingest/import_bosa as subprocess. Returns (imported_new, imported_updated, errors)."""
    from app.db.db_url import resolve_db_url
    resolved_db_url = resolve_db_url(db_url)
    cmd = [
        sys.executable,
        "-m",
        "ingest.import_bosa",
        str(file_path),
        "--db-url",
        resolved_db_url,
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        return (0, 0, 1)
    full_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
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
        description="Sync BOSA e-Procurement: search, save raw JSON, optionally import into DB.",
    )
    parser.add_argument(
        "--query",
        "--term",
        dest="query",
        default="travaux",
        help="Search term",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Page size (max notices to fetch)",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number (default: 1)",
    )
    parser.add_argument(
        "--out",
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for raw BOSA JSON (default: data/raw/bosa)",
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
        "--db-url",
        dest="db_url",
        default=None,
        help="Optional DATABASE_URL override for import step",
    )
    parser.add_argument(
        "--migrate",
        dest="do_migrate",
        action="store_true",
        default=True,
        help="Run database migrations before import (default: true)",
    )
    parser.add_argument(
        "--no-migrate",
        dest="do_migrate",
        action="store_false",
        help="Skip database migrations before import",
    )
    parser.add_argument(
        "--discover",
        dest="do_discover",
        action="store_true",
        default=True,
        help="Auto-run discovery if endpoints not confirmed (default: true)",
    )
    parser.add_argument(
        "--no-discover",
        dest="do_discover",
        action="store_false",
        help="Skip auto-discovery (will fail if endpoints not confirmed)",
    )
    parser.add_argument(
        "--force-discover",
        action="store_true",
        help="Force discovery and overwrite cached endpoints, then run search",
    )
    args = parser.parse_args()

    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Auto-discover endpoints if not confirmed (unless --no-discover)
    if args.force_discover or (args.do_discover and not _endpoints_confirmed()):
        try:
            from app.connectors.bosa.openapi_discovery import load_or_discover_endpoints, cache_path
            cache_file = cache_path()
            print(f"Running endpoint discovery (cache: {cache_file})...", file=sys.stderr)
            load_or_discover_endpoints(force=args.force_discover)
            print("Discovery complete.", file=sys.stderr)
        except Exception as e:
            print(f"BOSA discovery failed: {e}", file=sys.stderr)
            return 1

    page_size = max(1, args.limit)
    try:
        from app.connectors.bosa.client import search_publications
        result = search_publications(term=args.query, page=args.page, page_size=page_size)
    except Exception as e:
        print(f"BOSA search failed: {e}", file=sys.stderr)
        return 1

    fetched = _count_fetched(result)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
    raw_filename = f"bosa_{ts}.json"
    saved_path = out_dir / raw_filename
    with open(saved_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved raw: {saved_path} ({fetched} notices)")

    imported_new, imported_updated, errors = 0, 0, 0
    if args.do_import:
        from app.db.db_url import get_default_db_url, resolve_db_url
        effective_db_url = args.db_url or os.environ.get("DATABASE_URL") or get_default_db_url()
        effective_db_url = resolve_db_url(effective_db_url)
        if args.do_migrate:
            try:
                ensure_db_migrated(effective_db_url)
            except RuntimeError as e:
                print(f"Migration failed: {e}", file=sys.stderr)
                return 1
        imported_new, imported_updated, errors = run_import(saved_path, db_url=effective_db_url)
        print(f"Imported/updated {imported_new + imported_updated} notices")

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
