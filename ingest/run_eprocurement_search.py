#!/usr/bin/env python3
"""Run e-Procurement search via connectors (official API or Playwright fallback)."""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Optional: override provider via env (CLI --provider takes precedence)
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "publicprocurement"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run e-Procurement search (official API or Playwright fallback)."
    )
    parser.add_argument("term", nargs="?", default="travaux", help="Search term")
    parser.add_argument("page", nargs="?", type=int, default=1, help="Page number")
    parser.add_argument("page_size", nargs="?", type=int, default=25, help="Page size")
    parser.add_argument(
        "--provider",
        choices=("official", "playwright", "auto"),
        default=None,
        help="Override EPROC_MODE (official | playwright | auto)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Force endpoint discovery now, print selected endpoints, then run search",
    )
    parser.add_argument(
        "--force-discover",
        action="store_true",
        help="Same as --discover but overwrite cache file",
    )
    args = parser.parse_args()

    if args.provider is not None:
        os.environ["EPROC_MODE"] = args.provider

    if args.discover or args.force_discover:
        from connectors.eprocurement.openapi_discovery import load_or_discover_endpoints

        load_or_discover_endpoints(force=args.force_discover)
        if args.force_discover:
            print("Endpoint cache overwritten (--force-discover).")
        print("Discovery complete. Running search...")

    from connectors.eprocurement.client import search_publications

    try:
        result = search_publications(
            term=args.term,
            page=args.page,
            page_size=args.page_size,
        )
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        return 1

    # Same naming as existing collector: publicprocurement_<ISO>.json
    now = datetime.utcnow()
    ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
    filename = f"publicprocurement_{ts}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / filename

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out_path}")
    total = result.get("json", {}).get("totalCount")
    if total is not None:
        print(f"totalCount: {total}")
    # Quick check: response should contain publications or items (list with length > 0)
    data = result.get("json", result)
    has_publications = "publications" in data
    has_items = "items" in data
    has_results = "results" in data
    arr = data.get("publications") or data.get("items") or data.get("results") or []
    list_len = len(arr) if isinstance(arr, list) else 0
    print(f"Quick check: publications={has_publications} items={has_items} results={has_results} list_length={list_len}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
