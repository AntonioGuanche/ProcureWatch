#!/usr/bin/env python3
"""Import raw TED (Tenders Electronic Daily) search JSON into the database.
Usage: python ingest/import_ted.py <path_to_raw_ted_json> [--db-url DATABASE_URL]
Stores notices with source='ted.europa.eu', stable source_id, and TED notice URL.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging import setup_logging
from app.db.db_url import get_default_db_url, resolve_db_url
from app.models.notice import Notice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.utils.cpv import normalize_cpv

setup_logging()

SOURCE_NAME = "TED_EU"


def create_local_session(db_url: str | None = None):
    """Create a local sessionmaker for the given DB URL."""
    if db_url is None:
        db_url = get_default_db_url()
    else:
        db_url = resolve_db_url(db_url)
    
    engine = create_engine(db_url, pool_pre_ping=True, echo=False)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Try to import pycountry for country code normalization (optional)
try:
    import pycountry
    HAS_PYCOUNTRY = True
except ImportError:
    HAS_PYCOUNTRY = False


def pick_text(value: Any) -> str | None:
    """
    Extract text from multi-language dict or list.
    If value is str, return it.
    If dict, return value.get("eng") or value.get("fra") or first non-empty value.
    If list, return first non-empty item.
    Else return None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() if value.strip() else None
    if isinstance(value, dict):
        # Prefer ENG, then FRA, then any non-empty value
        for lang in ("eng", "ENG", "fra", "FRA", "en", "EN", "fr", "FR"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
        # Fallback: first non-empty string value
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(value, list):
        for item in value:
            result = pick_text(item)
            if result:
                return result
        return None
    return None


def normalize_country(code: Any) -> str | None:
    """
    Normalize country code to ISO2 (alpha_2).
    Accepts 2-letter, 3-letter codes, or list/tuple/set of codes.
    If list/tuple/set: iterate and return first that normalizes.
    If ISO2: return uppercase.
    If ISO3: map to ISO2 via pycountry if available, else fallback dict.
    Returns uppercase 2-letter code or None (never 'EU').
    """
    if not code:
        return None
    
    # Handle list/tuple/set: iterate and return first that normalizes
    if isinstance(code, (list, tuple, set)):
        for item in code:
            result = normalize_country(item)
            if result:
                return result
        return None
    
    # Convert to string and normalize
    code_str = str(code).strip().upper()
    if not code_str:
        return None
    
    # Reject 'EU' (not a valid country code)
    if code_str == "EU":
        return None
    
    # Already 2-letter ISO2
    if len(code_str) == 2:
        return code_str
    
    # 3-letter ISO3: try pycountry first
    if len(code_str) == 3:
        if HAS_PYCOUNTRY:
            try:
                country = pycountry.countries.get(alpha_3=code_str)
                if country and country.alpha_2:
                    return country.alpha_2.upper()
            except (KeyError, AttributeError):
                pass
        
        # Fallback dict for common EU countries (ISO3 -> ISO2)
        iso3_to_iso2 = {
            "BEL": "BE", "FRA": "FR", "DEU": "DE", "NLD": "NL", "LUX": "LU",
            "ESP": "ES", "ITA": "IT", "PRT": "PT", "IRL": "IE", "DNK": "DK",
            "SWE": "SE", "FIN": "FI", "AUT": "AT", "POL": "PL", "CZE": "CZ",
            "SVK": "SK", "SVN": "SI", "HRV": "HR", "ROU": "RO", "BGR": "BG",
            "GRC": "GR", "HUN": "HU", "MLT": "MT", "CYP": "CY", "EST": "EE",
            "LVA": "LV", "LTU": "LT",
        }
        if code_str in iso3_to_iso2:
            return iso3_to_iso2[code_str]
        
        # Unknown ISO3: return None (not 'EU')
        return None
    
    # Invalid length: return None
    return None


def extract_cpv_main(notice: dict[str, Any]) -> str | None:
    """
    Extract main CPV code from notice.
    Tries: main-classification-proc, classification-cpv, then any CPV-looking field.
    Returns numeric code string like "45000000" if found, else None.
    """
    # Try main-classification-proc first
    main = notice.get("main-classification-proc")
    if main is not None:
        raw = pick_text(main)
        if raw:
            # Extract digits only
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 8:
                return digits[:8]
    
    # Try classification-cpv
    cpv = notice.get("classification-cpv") or notice.get("cpv")
    if cpv is not None:
        raw = pick_text(cpv)
        if raw:
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 8:
                return digits[:8]
    
    # Try other common CPV fields
    for key in ("mainCpv", "cpvCode", "cpvMainCode", "mainCpvCode"):
        value = notice.get(key)
        if value is not None:
            raw = pick_text(value)
            if raw:
                digits = re.sub(r"\D", "", raw)
                if len(digits) >= 8:
                    return digits[:8]
    
    # Try CPV codes list
    codes = notice.get("cpvCodes") or notice.get("cpv")
    if isinstance(codes, list) and codes:
        for code_item in codes:
            raw = pick_text(code_item)
            if raw:
                digits = re.sub(r"\D", "", raw)
                if len(digits) >= 8:
                    return digits[:8]
    
    return None


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
    """Extract title from TED notice; handle multi-language dicts."""
    # Try notice-title (TED Search API field, may be dict)
    title = pick_text(notice.get("notice-title"))
    if title:
        return title[:500]
    # Try title-proc
    title = pick_text(notice.get("title-proc"))
    if title:
        return title[:500]
    # Try title-glo
    title = pick_text(notice.get("title-glo"))
    if title:
        return title[:500]
    # Fallback to other common field names
    title = pick_text(notice.get("title"))
    if title:
        return title[:500]
    for key in ("titles", "titleList"):
        items = notice.get(key)
        if items:
            title = pick_text(items)
            if title:
                return title[:500]
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
    """
    Country code (ISO2 e.g. BE); normalize from multiple fields in order.
    Checks: buyer-country, place-of-performance-country-proc, place-of-performance-country-lot, country-origin.
    Returns None if not found (no 'EU' fallback).
    """
    # Check fields in priority order
    fields_to_check = [
        "buyer-country",
        "place-of-performance-country-proc",
        "place-of-performance-country-lot",
        "country-origin",
    ]
    
    for field in fields_to_check:
        c = notice.get(field)
        if c:
            normalized = normalize_country(c)
            if normalized:
                return normalized
    
    # Fallback to other common field names
    c = notice.get("country") or notice.get("countryCode")
    if c:
        normalized = normalize_country(c)
        if normalized:
            return normalized
    
    authority = notice.get("contractingAuthority") or notice.get("buyer")
    if isinstance(authority, dict):
        c = authority.get("country") or authority.get("countryCode")
        if c:
            normalized = normalize_country(c)
            if normalized:
                return normalized
    
    return None


def _language(notice: dict[str, Any]) -> str | None:
    """Language code if present."""
    lang = notice.get("language") or notice.get("lang")
    if isinstance(lang, str) and len(lang) >= 2:
        return lang[:2].upper()
    return None


def _cpv_main(notice: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (cpv_8, display) normalized; use extract_cpv_main helper."""
    cpv_8 = extract_cpv_main(notice)
    if not cpv_8:
        return (None, None)
    # Create display format (8 digits)
    display = cpv_8
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
    pt = notice.get("procedure-type") or notice.get("procedureType") or notice.get("procurementProcedureType")
    if pt:
        pt_str = pick_text(pt) or (str(pt).strip() if isinstance(pt, str) else None)
        if pt_str:
            return pt_str[:100]
    return None


def _published_at(notice: dict[str, Any]) -> datetime | None:
    """Publication date from notice."""
    # Try publication-date (TED Search API field)
    val = notice.get("publication-date") or notice.get("publicationDate")
    if val:
        return parse_date(str(val))
    # Fallback to other common field names
    for key in ("dispatchDate", "date", "insertionDate"):
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
        print("[WARNING] Skipping notice without stable id")
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

    # Map to ProcurementNotice columns
    organisation_names = {"default": buyer_name} if buyer_name else None
    nuts_codes = [country] if country else None
    publication_languages = [language] if language else None
    publication_date = published_at.date() if published_at else None
    try:
        raw_data = json.loads(raw_json_str) if raw_json_str else None
    except (json.JSONDecodeError, TypeError):
        raw_data = None

    existing = db.query(Notice).filter(
        Notice.source == SOURCE_NAME,
        Notice.source_id == source_id,
    ).first()

    if existing:
        existing.title = title
        existing.organisation_names = organisation_names
        existing.nuts_codes = nuts_codes
        existing.publication_languages = publication_languages
        existing.cpv_main_code = cpv_main_code
        existing.notice_type = procedure_type
        existing.publication_date = publication_date
        existing.deadline = deadline_at
        existing.url = url
        existing.raw_data = raw_data
        existing.updated_at = now
        flag_modified(existing, "updated_at")
        notice_obj = existing
        print(f"  [Updated] {source_id}")
    else:
        notice_obj = Notice(
            source=SOURCE_NAME,
            source_id=source_id,
            publication_workspace_id=source_id,
            title=title,
            organisation_names=organisation_names,
            nuts_codes=nuts_codes,
            publication_languages=publication_languages,
            cpv_main_code=cpv_main_code,
            notice_type=procedure_type,
            publication_date=publication_date,
            deadline=deadline_at,
            url=url,
            raw_data=raw_data,
        )
        db.add(notice_obj)
        print(f"  [Created] {source_id}")

    try:
        db.commit()
        db.refresh(notice_obj)
    except IntegrityError as e:
        db.rollback()
        print(f"  [ERROR] Integrity error for {source_id}: {e}")
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
        print(f"  [WARNING] Error saving CPV additional for {source_id}: {e}")
    return True


def import_file(file_path: Path, db_sessionmaker: sessionmaker[Session]) -> tuple[int, int, int]:
    """
    Load raw TED JSON (as saved by sync_ted.py), import each notice.
    Returns (imported_new, imported_updated, errors).
    """
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return 0, 0, 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
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
        print("[WARNING] No notices list in file")
        return 0, 0, 0

    print(f"\n[Processing] {file_path}")
    print(f"[Found] {len(notices)} notices")
    db = db_sessionmaker()
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
        print(f"\n[Complete] Import complete: {created_count} created, {updated_count} updated")
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Error during import: {e}")
        raise
    finally:
        db.close()

    return created_count, updated_count, error_count


def import_ted_raw_files(raw_paths: list[Path], db_url: str | None = None) -> tuple[int, int, int]:
    """
    Import one or more TED raw JSON files.
    Wrapper around import_file for reuse from CLI or other callers.
    Returns cumulative (imported_new, imported_updated, errors).
    """
    db_sessionmaker = create_local_session(db_url)
    total_new = 0
    total_updated = 0
    total_errors = 0
    for path in raw_paths:
        created, updated, errors = import_file(path, db_sessionmaker)
        total_new += created
        total_updated += updated
        total_errors += errors
    return total_new, total_updated, total_errors


def main() -> None:
    # Configure stdout/stderr for UTF-8 encoding on Windows (when captured as subprocess)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Ignore if reconfigure fails
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Ignore if reconfigure fails

    parser = argparse.ArgumentParser(
        description="Import raw TED JSON files into the database"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Path(s) to raw TED JSON file(s)",
    )
    parser.add_argument(
        "--db-url",
        help="Optional DATABASE_URL override (default: DATABASE_URL env var or sqlite:///./dev.db)",
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    imported_new, imported_updated, errors = import_ted_raw_files(paths, db_url=args.db_url)
    summary = {
        "imported_new": imported_new,
        "imported_updated": imported_updated,
        "errors": errors,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
