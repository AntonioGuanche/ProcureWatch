#!/usr/bin/env python3
"""
Daily refresh for watchlists: recompute matches for each watchlist,
update last_refresh_at, print summary JSON.

Email notifications are NOT implemented yet (no notify_email field on
the Watchlist model). This will be added when user auth + notification
preferences are in place.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.db.crud.watchlists_mvp import (
    list_all_watchlists,
    list_new_since_for_watchlist,
    refresh_watchlist_matches,
    update_watchlist,
)


def refresh_one_watchlist(db: Any, watchlist: Any) -> dict[str, Any]:
    """
    Refresh matches for one watchlist:
    1. Recompute matches via refresh_watchlist_matches
    2. Count new notices (created since last_refresh_at)
    3. Update last_refresh_at
    Returns summary dict.
    """
    cutoff = watchlist.last_refresh_at
    match_result = refresh_watchlist_matches(db, watchlist)

    # Count new notices since last refresh
    new_count = 0
    if cutoff is not None:
        _, new_count = list_new_since_for_watchlist(db, watchlist, limit=0, offset=0)

    now = datetime.now(timezone.utc)
    update_watchlist(db, watchlist.id, last_refresh_at=now)

    return {
        "watchlist_id": watchlist.id,
        "watchlist_name": watchlist.name,
        "matched": match_result.get("matched", 0),
        "new_since_last_refresh": new_count,
        "first_run": cutoff is None,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Refresh watchlist matches and update last_refresh_at."
    )
    parser.add_argument(
        "--watchlist-id", type=str, default=None,
        help="Refresh only this watchlist UUID",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        watchlists = list_all_watchlists(db, args.watchlist_id)
        if not watchlists:
            print(json.dumps({"error": "No watchlists to refresh", "watchlists": []}))
            return 0
        results = []
        for wl in watchlists:
            summary = refresh_one_watchlist(db, wl)
            results.append(summary)
            print(f"  [{wl.name}] matched={summary['matched']}, new={summary['new_since_last_refresh']}")
        print(json.dumps({"watchlists": results}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
