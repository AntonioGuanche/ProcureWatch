#!/usr/bin/env python3
"""Seed script: backfill watchlists.sources column with default ["TED","BOSA"]."""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.db_url import get_default_db_url, resolve_db_url
from app.models.watchlist import Watchlist
from app.utils.sources import DEFAULT_SOURCES


def main() -> int:
    """Backfill watchlists.sources for NULL/empty values."""
    parser = argparse.ArgumentParser(description="Backfill watchlists.sources column")
    parser.add_argument(
        "--db-url",
        help="Optional DATABASE_URL override (default: DATABASE_URL env var or sqlite:///./dev.db)",
    )
    args = parser.parse_args()
    
    db_url = args.db_url or get_default_db_url()
    db_url = resolve_db_url(db_url)
    
    engine = create_engine(db_url, pool_pre_ping=True, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    try:
        default_sources_json = json.dumps(DEFAULT_SOURCES)
        
        # Find watchlists with NULL or empty sources
        watchlists = db.query(Watchlist).filter(
            (Watchlist.sources == None) | (Watchlist.sources == "") | (Watchlist.sources == "[]")
        ).all()
        
        if not watchlists:
            print("No watchlists need backfilling (all have sources set)")
            return 0
        
        print(f"Found {len(watchlists)} watchlist(s) to backfill")
        
        for wl in watchlists:
            wl.sources = default_sources_json
            print(f"  Updated watchlist '{wl.name}' (id: {wl.id})")
        
        db.commit()
        print(f"\nSuccessfully backfilled {len(watchlists)} watchlist(s) with sources={DEFAULT_SOURCES}")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
