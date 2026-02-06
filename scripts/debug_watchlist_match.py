#!/usr/bin/env python3
"""Debug script to show watchlist matching results for a specific watchlist."""
import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.db_url import get_default_db_url, resolve_db_url
from app.db.models.notice import Notice
from app.db.models.watchlist import Watchlist
from app.db.models.watchlist_match import WatchlistMatch
from app.db.models.notice_detail import NoticeDetail
from app.utils.searchable_text import build_searchable_text


def parse_sources(value):
    """
    Parse watchlist.sources to a list of strings.
    None -> []; list -> list; JSON string -> list; comma-separated string -> list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                return [str(x).strip() for x in parsed] if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in s.split(",") if x.strip()]
    return []


def safe_text(s: str, max_len: int = 200) -> str:
    """Return UTF-8-safe excerpt for Windows console: replace invalid bytes, normalize newlines, truncate."""
    if not s:
        return ""
    out = s.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    out = out.replace("\r", " ").replace("\n", " ")
    out = " ".join(out.split())
    return (out[:max_len] + "...") if len(out) > max_len else out


def main() -> int:
    """Debug watchlist matching."""
    # Windows-safe: avoid crash on console encoding
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Debug watchlist matching results"
    )
    parser.add_argument(
        "watchlist_id",
        help="Watchlist ID to debug",
    )
    parser.add_argument(
        "--db-url",
        help="Optional DATABASE_URL override (default: DATABASE_URL env var or sqlite:///./dev.db)",
    )
    args = parser.parse_args()

    watchlist_id = args.watchlist_id

    db_url = args.db_url or get_default_db_url()
    db_url = resolve_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
        if not watchlist:
            print(f"ERROR: Watchlist {watchlist_id} not found")
            return 1

        print(f"Watchlist: {watchlist.name}")
        print(f"Keywords: {watchlist.keywords or '(none)'}")
        print(f"Countries: {watchlist.countries or '(none)'}")
        print(f"CPV prefixes: {watchlist.cpv_prefixes or '(none)'}")
        print(f"Sources: {parse_sources(watchlist.sources)}")
        print()

        notices = db.query(Notice).order_by(Notice.created_at.desc()).limit(100).all()

        print(f"Checking {len(notices)} notices...")
        print()

        matched_count = 0
        for notice in notices:
            detail = db.query(NoticeDetail).filter(NoticeDetail.notice_id == notice.id).first()
            searchable_text = build_searchable_text(notice, detail)

            matched = db.query(WatchlistMatch).filter(
                WatchlistMatch.watchlist_id == watchlist_id,
                WatchlistMatch.notice_id == notice.id,
            ).first() is not None

            if matched:
                matched_count += 1
                print(f"[MATCHED] {notice.source}/{notice.source_id}")
                print(f"  Title: {notice.title}")
                print(f"  Country: {notice.country or '(none)'}")
                print(f"  CPV: {notice.cpv_main_code or '(none)'}")
                print(f"  Notice source: {notice.source}")
                print(f"  Searchable text excerpt: {safe_text(searchable_text)}")
                print()

        print(f"Total matched: {matched_count}/{len(notices)}")

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
