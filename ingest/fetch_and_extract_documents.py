#!/usr/bin/env python3
"""
Fetch and extract documents: download NoticeDocument files to local storage,
compute sha256, optionally extract text from PDFs.
Options: --notice-id, --watchlist-id, --limit-notices, --limit-documents-per-notice,
--only-missing (default true), --extract (default true), --storage-dir (default data/documents).
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.db.crud.notices import get_notice_by_id
from app.db.crud.watchlists_mvp import get_watchlist_by_id, list_notices_for_watchlist
from app.db.crud.notice_detail import (
    list_documents_by_notice_id,
    update_document_download_result,
    update_document_extraction_result,
)
from app.documents.downloader import download_document, infer_extension_from_file_type_or_url
from app.documents.pdf_extractor import extract_text_from_pdf


def _is_pdf(doc) -> bool:
    """True if document looks like a PDF (file_type or url)."""
    ft = (doc.file_type or "").lower()
    if "pdf" in ft:
        return True
    url = (doc.url or "").lower()
    return url.endswith(".pdf") or ".pdf?" in url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download notice documents to local storage and optionally extract PDF text.",
    )
    parser.add_argument("--notice-id", type=str, default=None, help="Process only this notice UUID")
    parser.add_argument(
        "--watchlist-id",
        type=str,
        default=None,
        help="Process notices matching this watchlist",
    )
    parser.add_argument(
        "--limit-notices",
        type=int,
        default=20,
        help="Max notices to process (default 20)",
    )
    parser.add_argument(
        "--limit-documents-per-notice",
        type=int,
        default=10,
        help="Max documents per notice (default 10)",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        default=True,
        help="Only download docs with local_path null or download_status != ok (default: true)",
    )
    parser.add_argument(
        "--no-only-missing",
        action="store_false",
        dest="only_missing",
        help="Process all documents",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        default=True,
        help="Extract text from PDFs after download (default: true)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_false",
        dest="extract",
        help="Skip PDF text extraction",
    )
    parser.add_argument(
        "--storage-dir",
        type=str,
        default="data/documents",
        help="Base directory for downloaded files (default data/documents)",
    )
    args = parser.parse_args()

    if not args.notice_id and not args.watchlist_id:
        print(json.dumps({"error": "Provide --notice-id or --watchlist-id"}))
        return 1
    if args.notice_id and args.watchlist_id:
        print(json.dumps({"error": "Provide only one of --notice-id or --watchlist-id"}))
        return 1

    storage_dir = Path(args.storage_dir)
    db = SessionLocal()
    try:
        notices_to_process = []
        if args.notice_id:
            notice = get_notice_by_id(db, args.notice_id)
            if notice:
                notices_to_process = [notice]
            else:
                print(json.dumps({"error": "Notice not found", "notice_id": args.notice_id}))
                return 1
        else:
            wl = get_watchlist_by_id(db, args.watchlist_id)
            if not wl:
                print(json.dumps({"error": "Watchlist not found", "watchlist_id": args.watchlist_id}))
                return 1
            notices_to_process, _ = list_notices_for_watchlist(
                db, wl, limit=args.limit_notices, offset=0
            )

        notices_processed = 0
        docs_attempted = 0
        downloaded_ok = 0
        extracted_ok = 0
        skipped = 0
        failed = 0

        for notice in notices_to_process:
            notices_processed += 1
            notice_id = str(notice.id)
            items, _ = list_documents_by_notice_id(
                db, notice_id, limit=args.limit_documents_per_notice, offset=0
            )
            for doc in items:
                if args.only_missing and doc.local_path and doc.download_status == "ok":
                    skipped += 1
                    continue
                docs_attempted += 1
                doc_id = str(doc.id)
                ext = infer_extension_from_file_type_or_url(doc.file_type, doc.url)
                dest_path = storage_dir / notice_id / f"{doc_id}.{ext}"

                # Download
                try:
                    meta = download_document(doc.url, dest_path, timeout_seconds=60)
                    update_document_download_result(
                        db,
                        doc_id,
                        local_path=str(dest_path),
                        content_type=meta.get("content_type"),
                        file_size=meta.get("file_size"),
                        sha256=meta.get("sha256"),
                        download_status="ok",
                        download_error=None,
                    )
                    downloaded_ok += 1
                except Exception as e:
                    update_document_download_result(
                        db,
                        doc_id,
                        local_path=None,
                        content_type=None,
                        file_size=None,
                        sha256=None,
                        download_status="failed",
                        download_error=str(e)[:2000],
                    )
                    failed += 1
                    continue

                # Extract PDF text if requested
                if args.extract and _is_pdf(doc):
                    try:
                        text = extract_text_from_pdf(dest_path)
                        update_document_extraction_result(
                            db,
                            doc_id,
                            extracted_text=text or "",
                            extraction_status="ok",
                            extraction_error=None,
                        )
                        extracted_ok += 1
                    except Exception as e:
                        update_document_extraction_result(
                            db,
                            doc_id,
                            extracted_text=None,
                            extraction_status="failed",
                            extraction_error=str(e)[:2000],
                        )
                        failed += 1

        summary = {
            "notices_processed": notices_processed,
            "docs_attempted": docs_attempted,
            "downloaded_ok": downloaded_ok,
            "extracted_ok": extracted_ok,
            "skipped": skipped,
            "failed": failed,
        }
        print(json.dumps(summary))
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
