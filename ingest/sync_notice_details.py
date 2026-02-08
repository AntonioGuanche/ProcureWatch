#!/usr/bin/env python3
"""
Sync publication details for notices: fetch detail JSON, store in notice_details,
extract and upsert lots and documents. Options: --notice-id, --watchlist-id,
--only-new-since (default true), --limit (default 50).
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from connectors.eprocurement.client import get_publication_detail
from connectors.eprocurement.detail_extractors import extract_documents, extract_lots
from app.db.session import SessionLocal
from app.db.crud.notices import get_notice_by_id
from app.db.crud.watchlists import get_watchlist_by_id, list_new_since_for_watchlist, list_notices_for_watchlist
from app.db.crud.notice_detail import (
    get_lot_ids_by_lot_number,
    upsert_documents_for_notice,
    upsert_lots_for_notice,
    upsert_notice_detail,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync publication details for notices (detail JSON, lots, documents).",
    )
    parser.add_argument("--notice-id", type=str, default=None, help="Sync only this notice UUID")
    parser.add_argument("--watchlist-id", type=str, default=None, help="Sync all notices matching this watchlist")
    parser.add_argument(
        "--only-new-since",
        action="store_true",
        default=True,
        help="Only sync notices newly seen since last_notified_at/last_refresh_at (default: true)",
    )
    parser.add_argument(
        "--no-only-new-since",
        action="store_false",
        dest="only_new_since",
        help="Sync all matching notices (ignore cutoff)",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max notices to process (default 50)")
    args = parser.parse_args()

    if not args.notice_id and not args.watchlist_id:
        print(json.dumps({"error": "Provide --notice-id or --watchlist-id"}))
        return 1
    if args.notice_id and args.watchlist_id:
        print(json.dumps({"error": "Provide only one of --notice-id or --watchlist-id"}))
        return 1

    db = SessionLocal()
    try:
        notices_to_sync: list[Any] = []
        if args.notice_id:
            notice = get_notice_by_id(db, args.notice_id)
            if notice:
                notices_to_sync = [notice]
            else:
                print(json.dumps({"error": "Notice not found", "notice_id": args.notice_id}))
                return 1
        else:
            wl = get_watchlist_by_id(db, args.watchlist_id)
            if not wl:
                print(json.dumps({"error": "Watchlist not found", "watchlist_id": args.watchlist_id}))
                return 1
            if args.only_new_since:
                notices_to_sync, _ = list_new_since_for_watchlist(db, wl, limit=args.limit, offset=0)
            else:
                notices_to_sync, _ = list_notices_for_watchlist(db, wl, limit=args.limit, offset=0)

        processed = 0
        fetched_ok = 0
        skipped = 0
        errors = 0
        lots_upserted = 0
        docs_upserted = 0

        for notice in notices_to_sync:
            processed += 1
            source_id = notice.source_id
            source = notice.source or "BOSA_EPROC"
            try:
                detail_json = get_publication_detail(source_id)
                if detail_json is None:
                    skipped += 1
                    continue
                raw_str = json.dumps(detail_json, ensure_ascii=False)
                upsert_notice_detail(db, str(notice.id), source, source_id, raw_str)
                fetched_ok += 1

                lots = extract_lots(detail_json)
                n_lots = upsert_lots_for_notice(db, str(notice.id), lots)
                lots_upserted += n_lots

                documents = extract_documents(detail_json)
                lot_numbers = list({d.get("lot_number") for d in documents if d.get("lot_number")})
                lot_number_to_id = get_lot_ids_by_lot_number(db, str(notice.id), lot_numbers)
                n_docs = upsert_documents_for_notice(db, str(notice.id), documents, lot_number_to_id)
                docs_upserted += n_docs
            except Exception as e:
                errors += 1
                # Continue with next notice
                continue

        summary = {
            "processed": processed,
            "fetched_ok": fetched_ok,
            "skipped": skipped,
            "errors": errors,
            "lots_upserted": lots_upserted,
            "docs_upserted": docs_upserted,
        }
        print(json.dumps(summary))
        return 0 if errors == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
