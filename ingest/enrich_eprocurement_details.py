#!/usr/bin/env python3
"""Enrich notices with buyer_name, deadline_at (and optionally lots/docs) from official API detail."""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session

from app.models.notice import Notice
from app.db.session import SessionLocal


SOURCE_NAME = "BOSA_EPROC"


def parse_date_from_detail(value: Any) -> Optional[datetime]:
    """Parse date from detail response (ISO string or similar)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def extract_buyer_from_detail(detail: dict[str, Any]) -> Optional[str]:
    """Best-effort extract buyer/contracting authority name from publication detail."""
    if not detail or not isinstance(detail, dict):
        return None
    # Common keys: buyer, contractingAuthority, organisation, etc.
    for key in ("buyer", "contractingAuthority", "contracting_authority", "organisation", "organization", "authority"):
        v = detail.get(key)
        if isinstance(v, dict):
            name = v.get("name") or v.get("legalName") or v.get("officialName")
            if name and isinstance(name, str):
                return name[:255].strip()
        if isinstance(v, str) and v.strip():
            return v[:255].strip()
    dossier = detail.get("dossier", {})
    if isinstance(dossier, dict):
        for key in ("buyer", "contractingAuthority", "organisation"):
            v = dossier.get(key)
            if isinstance(v, dict):
                name = v.get("name") or v.get("legalName")
                if name and isinstance(name, str):
                    return name[:255].strip()
            if isinstance(v, str) and v.strip():
                return v[:255].strip()
    return None


def extract_deadline_from_detail(detail: dict[str, Any]) -> Optional[datetime]:
    """Best-effort extract deadline from publication detail."""
    if not detail or not isinstance(detail, dict):
        return None
    for key in ("deadline", "receptionDeadline", "reception_deadline", "submissionDeadline", "submission_deadline", "deadlineDate", "deadline_at"):
        v = detail.get(key)
        if v is not None:
            d = parse_date_from_detail(v)
            if d:
                return d
    dossier = detail.get("dossier", {})
    if isinstance(dossier, dict):
        for key in ("deadline", "receptionDeadline", "submissionDeadline", "deadlineDate"):
            v = dossier.get(key)
            if v is not None:
                d = parse_date_from_detail(v)
                if d:
                    return d
    return None


def run_enrichment(
    db: Session,
    since_days: int = 2,
    limit: int = 200,
    provider: str = "auto",
) -> tuple[int, int]:
    """
    Enrich notices missing buyer_name or deadline_at using official API detail.
    Returns (enriched_count, skipped_count).
    """
    if provider != "official" and provider != "auto":
        print("Enrichment only supports official API; provider is", provider, "- skipping.")
        return (0, 0)

    try:
        from app.connectors.bosa.client import _get_client, reset_client
        reset_client()
        client, name = _get_client()
    except Exception as e:
        print("Could not get official client:", e, "- skipping enrichment.")
        return (0, 0)

    if name != "official":
        print("Provider is", name, "- enrichment requires official API. Skipping.")
        return (0, 0)

    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    query = (
        db.query(Notice)
        .filter(Notice.source == SOURCE_NAME)
        .filter((Notice.buyer_name.is_(None)) | (Notice.deadline_at.is_(None)))
        .filter(Notice.last_seen_at >= since)
        .order_by(Notice.last_seen_at.desc().nulls_last())
        .limit(limit)
    )
    notices = query.all()
    enriched = 0
    skipped = 0
    for notice in notices:
        detail = client.get_publication_detail(notice.source_id)
        if detail is None:
            skipped += 1
            continue
        updated = False
        if notice.buyer_name is None:
            buyer = extract_buyer_from_detail(detail)
            if buyer:
                notice.buyer_name = buyer
                updated = True
        if notice.deadline_at is None:
            deadline = extract_deadline_from_detail(detail)
            if deadline:
                notice.deadline_at = deadline
                updated = True
        if updated:
            enriched += 1
        else:
            skipped += 1
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print("Commit failed:", e)
        return (0, 0)
    return (enriched, skipped)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich notices with buyer_name/deadline from official API publication detail."
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=2,
        help="Consider notices seen in the last N days (default: 2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max notices to process (default: 200)",
    )
    parser.add_argument(
        "--provider",
        choices=("official", "playwright", "auto"),
        default="auto",
        help="Provider mode; only official performs detail fetch (default: auto)",
    )
    args = parser.parse_args()

    if args.provider is not None:
        os.environ["EPROC_MODE"] = args.provider

    db = SessionLocal()
    try:
        enriched, skipped = run_enrichment(
            db,
            since_days=args.since_days,
            limit=args.limit,
            provider=args.provider,
        )
        print(f"Enriched: {enriched}, Skipped/failed: {skipped}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
