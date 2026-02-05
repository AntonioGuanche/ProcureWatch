#!/usr/bin/env python3
"""
Daily refresh for watchlists: run sync for each enabled watchlist (or one by id),
early-stop when two consecutive pages yield no new/updated imports, then send
email digest for NEW notices (created_at > last_refresh_at) when notify_email is set.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.crud.watchlists import (
    get_new_since_cutoff,
    list_watchlists_for_refresh,
    list_new_notices_for_watchlist,
    count_new_notices_for_watchlist,
    update_watchlist,
)
from app.notifications.emailer import send_email


SYNC_SCRIPT = PROJECT_ROOT / "ingest" / "sync_eprocurement.py"
MAX_EMAIL_ITEMS = 30


def run_sync_page(term: str, page: int, page_size: int) -> dict[str, Any] | None:
    """Run sync_eprocurement.py for one page; return parsed summary or None on failure."""
    term = term or ""
    cmd = [
        sys.executable,
        str(SYNC_SCRIPT),
        "--term", term,
        "--page", str(page),
        "--page-size", str(page_size),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        stdout = (proc.stdout or "").strip()
        # Last line is JSON summary
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None
    except Exception:
        return None


def build_digest_body(watchlist_name: str, filters_summary: str, notices: list[Any], total_new: int) -> str:
    """Plain-text email body: watchlist name, filters, up to 30 notices (published_at, title, cpv_main_code, url, source_id)."""
    lines = [
        f"Watchlist: {watchlist_name}",
        filters_summary,
        "",
    ]
    for n in notices:
        pub = n.published_at.strftime("%Y-%m-%d %H:%M") if getattr(n, "published_at", None) else ""
        title = getattr(n, "title", "") or ""
        cpv = getattr(n, "cpv_main_code", "") or ""
        url = getattr(n, "url", "") or ""
        source_id = getattr(n, "source_id", "") or ""
        lines.append(f"  {pub}  {title}")
        lines.append(f"    CPV: {cpv}  source_id: {source_id}")
        lines.append(f"    {url}")
        lines.append("")
    if total_new > len(notices):
        lines.append(f"... and {total_new - len(notices)} more")
    return "\n".join(lines).strip()


def refresh_one_watchlist(
    db: Any,
    watchlist: Any,
    max_pages: int,
    page_size: int,
) -> dict[str, Any]:
    """
    Run sync for pages 1..max_pages with early-stop; update last_refresh_at/status;
    compute new notices and send email if notify_email set, not first run, and new > 0.
    Returns summary dict for the watchlist.
    """
    watchlist_id = watchlist.id
    term = watchlist.term or ""
    # Cutoff for "new since last run": last_notified_at (preferred) else last_refresh_at; None = first run
    cutoff = get_new_since_cutoff(watchlist)

    pages_fetched = 0
    fetched_total = 0
    imported_new_total = 0
    imported_updated_total = 0
    errors_total = 0
    consecutive_empty = 0

    for page in range(1, max_pages + 1):
        summary = run_sync_page(term, page, page_size)
        if summary is None:
            errors_total += 1
            consecutive_empty = 0
            continue
        pages_fetched += 1
        fetched_total += summary.get("fetched", 0)
        imported_new_total += summary.get("imported_new", 0)
        imported_updated_total += summary.get("imported_updated", 0)
        errors_total += summary.get("errors", 0)

        if summary.get("imported_new", 0) == 0 and summary.get("imported_updated", 0) == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0

    now = datetime.now(timezone.utc)
    status_str = json.dumps({
        "pages_fetched": pages_fetched,
        "fetched_total": fetched_total,
        "imported_new_total": imported_new_total,
        "imported_updated_total": imported_updated_total,
        "errors_total": errors_total,
    })
    update_watchlist(db, watchlist_id, last_refresh_at=now, last_refresh_status=status_str)

    # New notices: newly seen by ProcureWatch since cutoff (first_seen_at or created_at). Skip on first run.
    total_new = 0
    new_notices: list[Any] = []
    if cutoff is not None:
        new_notices = list_new_notices_for_watchlist(db, watchlist, cutoff, limit=MAX_EMAIL_ITEMS)
        total_new = count_new_notices_for_watchlist(db, watchlist, cutoff)

    # Send email only if: notify_email set, not first run (cutoff existed), new count > 0
    if watchlist.notify_email and cutoff is not None and total_new > 0:
        filters_parts = []
        if watchlist.term:
            filters_parts.append(f"term={watchlist.term}")
        if watchlist.cpv_prefix:
            filters_parts.append(f"cpv_prefix={watchlist.cpv_prefix}")
        if watchlist.buyer_contains:
            filters_parts.append(f"buyer_contains={watchlist.buyer_contains}")
        if watchlist.country:
            filters_parts.append(f"country={watchlist.country}")
        filters_summary = "Filters: " + ", ".join(filters_parts) if filters_parts else "Filters: (all)"
        subject = f"[ProcureWatch] {watchlist.name} — {total_new} new notices"
        body = build_digest_body(watchlist.name, filters_summary, new_notices, total_new)
        send_email(to=watchlist.notify_email, subject=subject, body=body)
        update_watchlist(db, watchlist_id, last_notified_at=now)
    elif watchlist.notify_email and cutoff is None:
        # First run: set last_notified_at anyway (do not send)
        update_watchlist(db, watchlist_id, last_notified_at=now)

    return {
        "watchlist_id": watchlist_id,
        "pages_fetched": pages_fetched,
        "fetched_total": fetched_total,
        "imported_new_total": imported_new_total,
        "imported_updated_total": imported_updated_total,
        "errors_total": errors_total,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Refresh watchlists: run sync per watchlist, optional email digest.")
    parser.add_argument("--watchlist-id", type=str, default=None, help="Refresh only this watchlist UUID")
    parser.add_argument("--max-pages", type=int, default=2, help="Max sync pages per watchlist (default 2); increase for deeper paging")
    parser.add_argument("--page-size", type=int, default=25, help="Page size for sync (default 25)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        watchlists = list_watchlists_for_refresh(db, args.watchlist_id)
        if not watchlists:
            print(json.dumps({"error": "No watchlists to refresh", "watchlists": []}))
            return 0
        results = []
        for wl in watchlists:
            summary = refresh_one_watchlist(db, wl, args.max_pages, args.page_size)
            results.append(summary)
        print(json.dumps({"watchlists": results}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
