#!/usr/bin/env python3
"""Run watchlist matching: find notices that match each watchlist and store new matches."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.watchlist_service import WatchlistService

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run watchlist matching (WatchlistService). Optionally run for one watchlist or all; dry-run skips persisting.",
        epilog="Example: python scripts/run_watchlists.py",
    )
    p.add_argument("--watchlist-id", default=None, help="Run for this watchlist only (default: all)")
    p.add_argument("--dry-run", action="store_true", help="Do not persist matches or update last_refresh_at")
    p.add_argument("--send-notifications", action="store_true", help="Send notifications for new matches (placeholder; no-op if no notify config)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    ts = datetime.now().strftime(DATE_FMT)

    db = SessionLocal()
    try:
        service = WatchlistService(db)
        total_new = 0
        if args.watchlist_id:
            result = service.find_matches(args.watchlist_id, dry_run=args.dry_run)
            if result.get("error"):
                print(f"{ts} [ERROR] {result['error']}")
                return 1
            new_count = result.get("new_matches", 0)
            total_new = new_count
            print(f"{ts} [INFO] Watchlist {args.watchlist_id}: {new_count} new matches")
            for n in result.get("notices", [])[:10]:
                print(f"  - {n.get('id')}: {n.get('title') or '(no title)'}")
            if new_count > 10:
                print(f"  ... and {new_count - 10} more")
        else:
            result = service.find_all_matches(dry_run=args.dry_run)
            total_new = result.get("total_new_matches", 0)
            n_wl = result.get("watchlists", 0)
            print(f"{ts} [INFO] Watchlists: {n_wl}, total new matches: {total_new}")
            for item in result.get("by_watchlist", []):
                print(f"  - {item.get('watchlist_name', item.get('watchlist_id'))}: {item.get('new_matches', 0)} new")
        if args.dry_run:
            print(f"{ts} [INFO] Dry run: no changes persisted")
        if args.send_notifications and total_new > 0 and not args.dry_run:
            print(f"{ts} [INFO] Send notifications: (no notify config in watchlist model)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
