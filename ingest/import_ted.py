#!/usr/bin/env python3
"""Import raw TED (Tenders Electronic Daily) search JSON into the database.
Usage: python ingest/import_ted.py <path_to_raw_ted_json>
Stores notices with source='ted.europa.eu', stable source_id, and TED notice URL.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging import setup_logging
from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.session import SessionLocal
from app.utils.cpv import normalize_cpv

setup_logging()

SOURCE_NAME = "ted.europa.eu"


def _pick_source_id(n: dict) -> str | None:
    """TED Search response includes publication-number reliably."""
    pub = n.get("publication-number")
    if isinstance(pub, str) and pub.strip():
        return pub.strip()
    return None


def _pick_url(n: dict) -> str | None:
    """Extract best notice URL from TED links (html, htmlDirect, pdf, xml); prefer ENG/FRA."""
    links = n.get("links")
    if not isinstance(links, dict):
        return None

    # Prefer HTML detail pages
    html = links.get("html")
    if isinstance(html, dict) and html:
        for lang in ("ENG", "FRA"):
            url = html.get(lang)
            if isinstance(url, str) and url.strip():
                return url.strip()
        for url in html.values():
            if isinstance(url, str) and url.strip():
                return url.strip()

    html_direct = links.get("htmlDirect")
    if isinstance(html_direct, dict) and html_direct:
        for lang in ("ENG", "FRA"):
            url = html_direct.get(lang)
            if isinstance(url, str) and url.strip():
                return url.strip()
        for url in html_direct.values():
            if isinstance(url, str) and url.strip():
                return url.strip()

    # fallback to PDF
    pdf = links.get("pdf")
    if isinstance(pdf, dict) and pdf:
        for lang in ("ENG", "FRA"):
            url = pdf.get(lang)
            if isinstance(url, str) and url.strip():
                return url.strip()
        for url in pdf.values():
            if isinstance(url, str) and url.strip():
                return url.strip()

    # fallback to XML
    xml = links.get("xml")
    if isinstance(xml, dict) and xml:
        for url in xml.values():
            if isinstance(url, str) and url.strip():
                return url.strip()

    return None


def parse_date(date_str: str | None) -> datetime | None:
    """Parse ISO or YYYY-MM-DD date string to datetime (timezone-aware UTC)."""
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _notice_id(notice: dict[str, Any]) -> str | None:
    """Stable TED identifier for source_id; prefer publication-number from TED Search."""
    sid = _pick_source_id(notice)
    if sid:
        return sid
    raw = notice.get("noticeId") or notice.get("id") or notice.get("notice_id")
    if raw is not None:
        return str(raw).strip() or None
    meta = notice.get("metadata")
    if isinstance(meta, dict):
        raw = meta.get("noticeId")
        if raw is not None:
            return str(raw).strip() or None
    return None


def _title(notice: dict[str, Any]) -> str:
    """Extract title from TED notice."""
    t = notice.get("title")
    if isinstance(t, str) and t.strip():
        return t[:500]
    for key in ("titles", "titleList"):
        items = notice.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    text = item.get("value") or item.get("text") or ""
                    if isinstance(text, str) and text.strip():
                        return text[:500]
    return "Untitled"


def _buyer_name(notice: dict[str, Any]) -> str | None:
    """Extract contracting authority / buyer name."""
    authority = (
        notice.get("contractingAuthority")
        or notice.get("buyer")
        or notice.get("organisation")
        or notice.get("authority")
    )
    if isinstance(authority, dict):
        name = authority.get("name") or authority.get("legalName") or authority.get("officialName")
        if name:
            return str(name)[:255]
    if isinstance(authority, str) and authority.strip():
        return authority.strip()[:255]
    return None


def _country(notice: dict[str, Any]) -> str | None:
    """Country code (ISO2 e.g. BE); prefer buyer-country / country, else from authority, else None (caller may use 'EU')."""
    # TED Search API field (from DEFAULT_FIELDS)
    c = notice.get("buyer-country") or notice.get("country") or notice.get("countryCode")
    if isinstance(c, str) and len(c) >= 2:
        return c[:2].upper()
    authority = notice.get("contractingAuthority") or notice.get("buyer")
    if isinstance(authority, dict):
        c = authority.get("country") or authority.get("countryCode")
        if isinstance(c, str) and len(c) >= 2:
            return c[:2].upper()
    return None


def _language(notice: dict[str, Any]) -> str | None:
    """Language code if present."""
    lang = notice.get("language") or notice.get("lang")
    if isinstance(lang, str) and len(lang) >= 2:
        return lang[:2].upper()
    return None


def _cpv_main(notice: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (cpv_8, display) normalized; strip hyphens from raw."""
    raw = None
    main = notice.get("mainCpv") or notice.get("cpvCode") or notice.get("cpvMainCode")
    if isinstance(main, dict):
        raw = (main.get("code") or main.get("value") or "").strip() or None
    elif isinstance(main, str) and main.strip():
        raw = main.strip()
    if not raw:
        codes = notice.get("cpvCodes") or notice.get("cpv") or []
        if isinstance(codes, list) and codes:
            first = codes[0]
            if isinstance(first, dict):
                raw = (first.get("code") or first.get("value") or "").strip() or None
            elif isinstance(first, str):
                raw = first.strip() or None
    if not raw:
        return (None, None)
    cpv_8, _, display = normalize_cpv(raw)
    return (cpv_8, display)


def _cpv_additional(notice: dict[str, Any]) -> list[str]:
    """Additional CPV codes as normalized 8-digit list."""
    out = []
    for key in ("additionalCpvs", "cpvAdditionalCodes"):
        items = notice.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                raw = (item.get("code") or item.get("value") or "").strip()
            elif isinstance(item, str):
                raw = item.strip()
            else:
                continue
            if raw:
                cpv_8, _, _ = normalize_cpv(raw)
                if cpv_8:
                    out.append(cpv_8)
    return out


def _procedure_type(notice: dict[str, Any]) -> str | None:
    """Procedure type string if present."""
    pt = notice.get("procedureType") or notice.get("procurementProcedureType")
    if isinstance(pt, str) and pt.strip():
        return pt.strip()[:100]
    return None


def _published_at(notice: dict[str, Any]) -> datetime | None:
    """Publication date from notice."""
    for key in ("publicationDate", "dispatchDate", "date", "insertionDate"):
        val = notice.get(key)
        if val:
            return parse_date(str(val))
    return None


def _deadline_at(notice: dict[str, Any]) -> datetime | None:
    """Deadline date from notice."""
    for key in ("deadlineDate", "deadline", "submissionDeadline"):
        val = notice.get(key)
        if val:
            return parse_date(str(val))
    return None


def _ted_url(notice_id: str | None, notice: dict[str, Any]) -> str:
    """Best-effort TED viewer URL: prefer links (html/htmlDirect/pdf/xml), else url/link, else derived from id."""
    url = _pick_url(notice)
    if url and url.startswith("http"):
        return url[:1000]
    url = notice.get("url") or notice.get("link") or notice.get("noticeUrl")
    if isinstance(url, str) and url.strip().startswith("http"):
        return url.strip()[:1000]
    if notice_id:
        return f"https://ted.europa.eu/udl?uri=TED:NOTICE:{notice_id}"[:1000]
    return "https://ted.europa.eu"


def import_notice(db: Session, notice: dict[str, Any], raw_json_str: str) -> bool:
    """Import a single TED notice; dedupe by (source, source_id). Returns True on success."""
    source_id = _notice_id(notice)
    if not source_id:
        print("⚠️  Skipping notice without stable id")
        return False

    now = datetime.now(timezone.utc)
    title = _title(notice)
    buyer_name = _buyer_name(notice)
    country = _country(notice) or "EU"
    language = _language(notice)
    cpv_main_code, cpv_display = _cpv_main(notice)
    cpv_additional_codes = _cpv_additional(notice)
    procedure_type = _procedure_type(notice)
    published_at = _published_at(notice)
    deadline_at = _deadline_at(notice)
    url = _ted_url(source_id, notice)

    existing = db.query(Notice).filter(
        Notice.source == SOURCE_NAME,
        Notice.source_id == source_id,
    ).first()

    if existing:
        # Touch semantics: always refresh last_seen_at and updated_at on re-import
        existing.title = title
        existing.buyer_name = buyer_name
        existing.country = country
        existing.language = language
        existing.cpv = cpv_display
        existing.cpv_main_code = cpv_main_code
        existing.procedure_type = procedure_type
        existing.published_at = published_at
        existing.deadline_at = deadline_at
        existing.url = url
        existing.raw_json = raw_json_str
        existing.last_seen_at = now
        existing.updated_at = now
        flag_modified(existing, "last_seen_at")
        flag_modified(existing, "updated_at")
        notice_obj = existing
        print(f"  ↻ Updated: {source_id}")
    else:
        notice_obj = Notice(
            source=SOURCE_NAME,
            source_id=source_id,
            title=title,
            buyer_name=buyer_name,
            country=country,
            language=language,
            cpv=cpv_display,
            cpv_main_code=cpv_main_code,
            procedure_type=procedure_type,
            published_at=published_at,
            deadline_at=deadline_at,
            url=url,
            raw_json=raw_json_str,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(notice_obj)
        print(f"  ✓ Created: {source_id}")

    try:
        db.commit()
        db.refresh(notice_obj)
    except IntegrityError as e:
        db.rollback()
        print(f"  ✗ Integrity error for {source_id}: {e}")
        return False

    db.query(NoticeCpvAdditional).filter(
        NoticeCpvAdditional.notice_id == notice_obj.id
    ).delete()
    for cpv_code in cpv_additional_codes:
        db.add(NoticeCpvAdditional(notice_id=notice_obj.id, cpv_code=cpv_code))
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  Error saving CPV additional for {source_id}: {e}")
    return True


def import_file(file_path: Path) -> tuple[int, int, int]:
    """
    Load raw TED JSON (as saved by sync_ted.py), import each notice.
    Returns (imported_new, imported_updated, errors).
    """
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return 0, 0, 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return 0, 0, 1

    raw = data.get("json", data)
    notices = (
        raw.get("notices")
        or raw.get("results")
        or raw.get("items")
        or raw.get("data")
        or []
    )
    if not isinstance(notices, list):
        print("⚠️  No notices list in file")
        return 0, 0, 0

    print(f"\n📂 Processing: {file_path}")
    print(f"📊 Found {len(notices)} notices")
    db = SessionLocal()
    created_count = 0
    updated_count = 0
    error_count = 0

    try:
        for idx, notice in enumerate(notices, 1):
            if not isinstance(notice, dict):
                continue
            print(f"\n[{idx}/{len(notices)}] ", end="")
            raw_json_str = json.dumps(notice, ensure_ascii=False)
            source_id = _notice_id(notice)
            is_new = False
            if source_id:
                is_new = db.query(Notice).filter(
                    Notice.source == SOURCE_NAME,
                    Notice.source_id == source_id,
                ).first() is None
            success = import_notice(db, notice, raw_json_str)
            if success:
                if is_new:
                    created_count += 1
                else:
                    updated_count += 1
            else:
                error_count += 1
        print(f"\n✅ Import complete: {created_count} created, {updated_count} updated")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error during import: {e}")
        raise
    finally:
        db.close()

    return created_count, updated_count, error_count


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python ingest/import_ted.py <path_to_raw_ted_json>")
        print("Example: python ingest/import_ted.py data/raw/ted/ted_2026-02-03T12-00-00-000Z.json")
        sys.exit(1)
    file_path = Path(sys.argv[1])
    imported_new, imported_updated, errors = import_file(file_path)
    summary = {
        "imported_new": imported_new,
        "imported_updated": imported_updated,
        "errors": errors,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
