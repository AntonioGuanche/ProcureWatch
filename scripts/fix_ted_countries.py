#!/usr/bin/env python3
"""Fix TED notices: update country from NULL or 'EU' to ISO2 from raw_json['buyer-country']."""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.db_url import get_default_db_url, resolve_db_url
from app.db.models.notice import Notice
from ingest.import_ted import normalize_country


def main() -> int:
    """Fix TED notices with NULL or 'EU' country."""
    parser = argparse.ArgumentParser(description="Fix TED notice countries from raw_json")
    parser.add_argument(
        "--db-url",
        help="Optional DATABASE_URL override (default: DATABASE_URL env var or sqlite:///./dev.db)",
    )
    args = parser.parse_args()
    
    db_url = args.db_url or get_default_db_url()
    db_url = resolve_db_url(db_url)
    
    # Run migrations first
    import subprocess
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": db_url},
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: Migrations failed: {result.stderr}", file=sys.stderr)
    
    engine = create_engine(db_url, pool_pre_ping=True, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    try:
        # Find TED notices with NULL or 'EU' country
        notices = db.query(Notice).filter(
            Notice.source == "ted.europa.eu",
            (Notice.country == None) | (Notice.country == "EU"),
        ).all()
        
        if not notices:
            print("No TED notices found with NULL or 'EU' country")
            return 0
        
        print(f"Found {len(notices)} TED notice(s) to fix")
        
        fixed_count = 0
        skipped_count = 0
        
        for notice in notices:
            if not notice.raw_json:
                skipped_count += 1
                continue
            
            try:
                raw_data = json.loads(notice.raw_json)
                buyer_country = raw_data.get("buyer-country")
                
                if buyer_country:
                    normalized = normalize_country(buyer_country)
                    if normalized:
                        notice.country = normalized
                        fixed_count += 1
                        print(f"  Fixed {notice.source_id}: {notice.country}")
                    else:
                        skipped_count += 1
                        print(f"  Skipped {notice.source_id}: could not normalize {buyer_country}")
                else:
                    skipped_count += 1
                    print(f"  Skipped {notice.source_id}: no buyer-country in raw_json")
            except (json.JSONDecodeError, Exception) as e:
                skipped_count += 1
                print(f"  Skipped {notice.source_id}: error parsing raw_json: {e}")
        
        if fixed_count > 0:
            db.commit()
            print(f"\nSuccessfully fixed {fixed_count} notice(s)")
        else:
            print(f"\nNo notices were fixed ({skipped_count} skipped)")
        
        if skipped_count > 0:
            print(f"Skipped {skipped_count} notice(s)")
        
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
