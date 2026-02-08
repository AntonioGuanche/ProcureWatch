#!/usr/bin/env python3
"""Import publicprocurement.be JSON files into the database."""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.models.notice import Notice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.session import SessionLocal, engine
from app.utils.cpv import normalize_cpv

# Setup logging
setup_logging()

SOURCE_NAME = "BOSA_EPROC"


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not date_str:
        return None
    try:
        # Try ISO format first
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Try YYYY-MM-DD format
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def extract_title(publication: Dict[str, Any]) -> str:
    """Extract title from publication."""
    dossier = publication.get("dossier", {})
    titles = dossier.get("titles", [])
    if titles:
        # Prefer French, then English, then first available
        for lang in ["FR", "EN", "NL", "DE"]:
            for title_obj in titles:
                if title_obj.get("language") == lang:
                    return title_obj.get("text", "")[:500]
        # Fallback to first title
        if titles:
            return titles[0].get("text", "")[:500]
    return "Untitled"


def extract_buyer_name(publication: Dict[str, Any]) -> Optional[str]:
    """Extract buyer name from publication."""
    # The API might not expose buyer directly, check various fields
    dossier = publication.get("dossier", {})
    # Check if there's a buyer field somewhere
    buyer = publication.get("buyer") or dossier.get("buyer")
    if isinstance(buyer, dict):
        return buyer.get("name") or buyer.get("legalName")
    if isinstance(buyer, str):
        return buyer[:255]
    return None


def extract_cpv_main_code(publication: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract main CPV code. Returns (cpv_8, display) using normalize_cpv.
    cpv_8: 8 digits for storage; display: "########-#" or "########" for display.
    """
    cpv_main = publication.get("cpvMainCode")
    raw = None
    if isinstance(cpv_main, dict):
        raw = (cpv_main.get("code") or "").strip() or None
    if not raw:
        return (None, None)
    cpv_8, _, display = normalize_cpv(raw)
    return (cpv_8, display)


def extract_cpv_additional_codes(publication: Dict[str, Any]) -> List[str]:
    """Extract additional CPV codes as 8-digit cpv_8 (normalized)."""
    codes: List[str] = []
    cpv_additional = publication.get("cpvAdditionalCodes", [])
    for cpv_obj in cpv_additional:
        if isinstance(cpv_obj, dict):
            raw = (cpv_obj.get("code") or "").strip()
            if raw:
                cpv_8, _, _ = normalize_cpv(raw)
                if cpv_8:
                    codes.append(cpv_8)
    return codes


def extract_url(publication: Dict[str, Any]) -> str:
    """Extract URL or construct it."""
    # Check for shortlink first
    shortlink = publication.get("shortlink")
    if shortlink:
        return f"https://www.publicprocurement.be{shortlink}"
    
    # Check for noticeIds to construct URL
    notice_ids = publication.get("noticeIds", [])
    if notice_ids:
        notice_id = notice_ids[0]
        return f"https://www.publicprocurement.be/bda/publication/{notice_id}"
    
    # Fallback to base URL
    return "https://www.publicprocurement.be/bda"


def import_publication(db: Session, publication: Dict[str, Any], raw_json_str: str) -> bool:
    """Import a single publication into the database."""
    dossier = publication.get("dossier", {})
    external_id = dossier.get("referenceNumber") or dossier.get("number") or publication.get("id")
    
    if not external_id:
        print("⚠️  Skipping publication without external_id")
        return False

    # Extract fields (CPV normalized: cpv_8 for storage, display for cpv field)
    title = extract_title(publication)
    buyer_name = extract_buyer_name(publication)
    cpv_main_code, cpv_display = extract_cpv_main_code(publication)
    cpv_additional_codes = extract_cpv_additional_codes(publication)
    procedure_type = dossier.get("procurementProcedureType")
    publication_date = parse_date(publication.get("dispatchDate") or publication.get("insertionDate"))
    deadline_date = parse_date(publication.get("deadlineDate"))
    url = extract_url(publication)

    # Check if notice already exists
    existing = db.query(Notice).filter(
        Notice.source == SOURCE_NAME,
        Notice.source_id == str(external_id)
    ).first()

    now = datetime.utcnow()

    # Map to ProcurementNotice columns
    organisation_names = {"default": buyer_name} if buyer_name else None
    nuts_codes = ["BE"]
    pub_date = publication_date.date() if hasattr(publication_date, 'date') and publication_date else publication_date
    try:
        raw_data = json.loads(raw_json_str) if raw_json_str else None
    except (json.JSONDecodeError, TypeError):
        raw_data = None

    if existing:
        # Update existing notice
        existing.title = title
        existing.organisation_names = organisation_names
        existing.nuts_codes = nuts_codes
        existing.cpv_main_code = cpv_main_code
        existing.notice_type = procedure_type
        existing.publication_date = pub_date
        existing.deadline = deadline_date
        existing.url = url
        existing.raw_data = raw_data
        existing.updated_at = now
        
        notice = existing
        print(f"  ↻ Updated: {external_id}")
    else:
        # Create new notice
        notice = Notice(
            source=SOURCE_NAME,
            source_id=str(external_id),
            publication_workspace_id=str(external_id),
            title=title,
            organisation_names=organisation_names,
            nuts_codes=nuts_codes,
            publication_languages=["FR"],
            cpv_main_code=cpv_main_code,
            notice_type=procedure_type,
            publication_date=pub_date,
            deadline=deadline_date,
            url=url,
            raw_data=raw_data,
        )
        db.add(notice)
        print(f"  ✓ Created: {external_id}")

    # Commit to get the notice ID
    try:
        db.commit()
        db.refresh(notice)
    except IntegrityError as e:
        db.rollback()
        print(f"  ✗ Integrity error for {external_id}: {e}")
        return False

    # Handle additional CPV codes
    # Delete existing additional CPV codes for this notice
    db.query(NoticeCpvAdditional).filter(
        NoticeCpvAdditional.notice_id == notice.id
    ).delete()

    # Insert new additional CPV codes
    for cpv_code in cpv_additional_codes:
        cpv_additional = NoticeCpvAdditional(
            notice_id=notice.id,
            cpv_code=cpv_code,
        )
        db.add(cpv_additional)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  Error saving CPV additional codes for {external_id}: {e}")

    return True


def import_file(file_path: Path) -> None:
    """Import a JSON file into the database."""
    print(f"\n📂 Processing: {file_path}")

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return

    # Extract metadata and publications
    # Handle both formats: {metadata: {...}, json: {...}} and direct {publications: [...]}
    metadata = data.get("metadata", {})
    json_data = data.get("json", data)  # Fallback to root if no json key
    
    # If json_data has publications, use it; otherwise check root level
    publications = json_data.get("publications", [])
    if not publications and isinstance(data, dict) and "publications" in data:
        publications = data.get("publications", [])
    if not publications:
        print("⚠️  No publications found in file")
        return

    print(f"📊 Found {len(publications)} publications")
    print(f"📋 Metadata: term={metadata.get('term')}, page={metadata.get('page')}, totalCount={metadata.get('totalCount')}")

    db = SessionLocal()
    created_count = 0
    updated_count = 0

    try:
        for idx, publication in enumerate(publications, 1):
            print(f"\n[{idx}/{len(publications)}] ", end="")
            raw_json_str = json.dumps(publication, ensure_ascii=False)
            
            # Check if exists before import
            dossier = publication.get("dossier", {})
            external_id = dossier.get("referenceNumber") or dossier.get("number") or publication.get("id")
            
            is_new = False
            if external_id:
                existing = db.query(Notice).filter(
                    Notice.source == SOURCE_NAME,
                    Notice.source_id == str(external_id)
                ).first()
                
                is_new = existing is None
            
            success = import_publication(db, publication, raw_json_str)
            
            if success:
                if is_new:
                    created_count += 1
                else:
                    updated_count += 1

        print(f"\n✅ Import complete: {created_count} created, {updated_count} updated")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during import: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python ingest/import_publicprocurement.py <json_file_path>")
        print("Example: python ingest/import_publicprocurement.py data/raw/publicprocurement/publicprocurement_2026-01-28.json")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    import_file(file_path)


if __name__ == "__main__":
    main()
