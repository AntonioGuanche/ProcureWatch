#!/usr/bin/env python3
"""Import raw BOSA e-Procurement search JSON into the database.
Usage: python ingest/import_bosa.py <path_to_raw_bosa_json> [--db-url DATABASE_URL]
Stores notices with source='bosa.eprocurement', stable source_id, and mapped fields.
"""
from __future__ import annotations

import argparse
import json
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
from app.db.models.notice import Notice
from app.db.models.notice_cpv_additional import NoticeCpvAdditional
from app.utils.cpv import normalize_cpv

setup_logging()

SOURCE_NAME = "bosa.eprocurement"
DEFAULT_COUNTRY = "BE"


def create_local_session(db_url: str | None = None):
    """Create a local sessionmaker for the given DB URL."""
    if db_url is None:
        db_url = get_default_db_url()
    else:
        db_url = resolve_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True, echo=False)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _pick_text(value: Any) -> str | None:
    """Extract text from multi-language dict or string. Prefer fr/nl/en."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() if value.strip() else None
    if isinstance(value, dict):
        for lang in ("fr", "nl", "en", "FR", "NL", "EN", "fra", "nld", "eng"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return _pick_text(first)
        if isinstance(first, str):
            return first.strip() if first.strip() else None
    return None


def _source_id(pub: dict[str, Any]) -> str | None:
    """Stable unique id from BOSA publication (publication id / notice id)."""
    for key in ("id", "publicationId", "publication_id", "noticeId", "notice_id"):
        v = pub.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _title(pub: dict[str, Any]) -> str:
    """Best available title (multi-language safe)."""
    for key in ("title", "name", "object", "description", "subject"):
        v = pub.get(key)
        text = _pick_text(v)
        if text:
            return text[:500]
    return "Sans titre"  # Fallback


def _buyer_name(pub: dict[str, Any]) -> str | None:
    """Contracting authority name."""
    for key in (
        "contractingAuthority",
        "contractingAuthorityName",
        "buyer",
        "organisation",
        "authority",
    ):
        v = pub.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:255]
        text = _pick_text(v) if isinstance(v, (dict, list)) else None
        if text:
            return text[:255]
    return None


def _cpv_codes(pub: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    """Return (cpv_main_code, cpv_display, additional_codes)."""
    main_code = None
    display = None
    additional: list[str] = []

    # Main CPV
    for key in ("mainCpv", "cpvMainCode", "cpv", "mainCpvCode", "main_classification"):
        v = pub.get(key)
        if v is None:
            continue
        raw = _pick_text(v) if not isinstance(v, str) else v
        if raw:
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 8:
                main_code = normalize_cpv(digits[:8]) or digits[:8]
                display = main_code
                break

    # List of CPV (e.g. cpvCodes, classifications)
    for key in ("cpvCodes", "cpv", "classifications", "additionalCpv"):
        v = pub.get(key)
        if not isinstance(v, list):
            continue
        for item in v:
            raw = _pick_text(item) if isinstance(item, dict) else (item if isinstance(item, str) else None)
            if raw:
                digits = re.sub(r"\D", "", raw)
                if len(digits) >= 8:
                    code = normalize_cpv(digits[:8]) or digits[:8]
                    if code and code not in additional:
                        if not main_code:
                            main_code = code
                            display = code
                        else:
                            additional.append(code)
    return (main_code, display, additional)


def _procedure_type(pub: dict[str, Any]) -> str | None:
    """Procedure type if present."""
    for key in ("procedureType", "procedure_type", "typeOfProcedure", "procedure"):
        v = pub.get(key)
        if v is None:
            continue
        text = _pick_text(v) if not isinstance(v, str) else v
        if isinstance(text, str) and text.strip():
            return text.strip()[:100]
    return None


def _parse_datetime(value: Any) -> datetime | None:
    """Parse ISO or numeric timestamp to datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s.replace("Z", "+00:00")[:26], fmt.replace("Z", "%z") if "%z" in fmt else fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _published_at(pub: dict[str, Any]) -> datetime | None:
    for key in ("publicationDate", "publishedAt", "publication_date", "createdAt", "date"):
        v = pub.get(key)
        if v is not None:
            parsed = _parse_datetime(v)
            if parsed:
                return parsed
    return None


def _deadline_at(pub: dict[str, Any]) -> datetime | None:
    for key in ("submissionDeadline", "deadline", "deadlineAt", "submission_deadline", "closingDate"):
        v = pub.get(key)
        if v is not None:
            parsed = _parse_datetime(v)
            if parsed:
                return parsed
    return None


def _url(pub: dict[str, Any], source_id: str) -> str:
    """Direct link if present, else placeholder."""
    for key in ("url", "link", "publicUrl", "detailUrl", "noticeUrl"):
        v = pub.get(key)
        if isinstance(v, str) and v.strip().startswith("http"):
            return v.strip()[:1000]
    # Placeholder
    return f"https://public.fedservices.be/publication/{source_id}"[:1000]


def import_publication(
    db: Session,
    pub: dict[str, Any],
    raw_json_str: str,
) -> bool:
    """Map one BOSA publication to Notice and upsert. Returns True on success."""
    source_id = _source_id(pub)
    if not source_id:
        return False

    now = datetime.now(timezone.utc)
    title = _title(pub)
    buyer_name = _buyer_name(pub)
    country = DEFAULT_COUNTRY
    cpv_main_code, cpv_display, cpv_additional_codes = _cpv_codes(pub)
    procedure_type = _procedure_type(pub)
    published_at = _published_at(pub)
    deadline_at = _deadline_at(pub)
    url = _url(pub, source_id)

    existing = db.query(Notice).filter(
        Notice.source == SOURCE_NAME,
        Notice.source_id == source_id,
    ).first()

    if existing:
        existing.title = title
        existing.buyer_name = buyer_name
        existing.country = country
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
    else:
        notice_obj = Notice(
            source=SOURCE_NAME,
            source_id=source_id,
            title=title,
            buyer_name=buyer_name,
            country=country,
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

    try:
        db.commit()
        db.refresh(notice_obj)
    except IntegrityError:
        db.rollback()
        return False

    db.query(NoticeCpvAdditional).filter(NoticeCpvAdditional.notice_id == notice_obj.id).delete()
    for code in cpv_additional_codes:
        db.add(NoticeCpvAdditional(notice_id=notice_obj.id, cpv_code=code))
    try:
        db.commit()
    except Exception:
        db.rollback()
    return True


def import_file(file_path: Path, db_sessionmaker: sessionmaker[Session]) -> tuple[int, int, int]:
    """
    Load raw BOSA JSON (as saved by sync_bosa.py). Returns (imported_new, imported_updated, errors).
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
    items = (
        raw.get("publications")
        or raw.get("items")
        or raw.get("results")
        or raw.get("data")
        or []
    )
    if not isinstance(items, list):
        print("[WARNING] No publications/items list in file")
        return 0, 0, 0

    db = db_sessionmaker()
    created_count = 0
    updated_count = 0
    error_count = 0

    try:
        for idx, pub in enumerate(items, 1):
            if not isinstance(pub, dict):
                continue
            raw_json_str = json.dumps(pub, ensure_ascii=False)
            source_id = _source_id(pub)
            is_new = (
                db.query(Notice).filter(
                    Notice.source == SOURCE_NAME,
                    Notice.source_id == source_id,
                ).first() is None
                if source_id
                else True
            )
            if import_publication(db, pub, raw_json_str):
                if is_new:
                    created_count += 1
                else:
                    updated_count += 1
            else:
                error_count += 1
    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()

    return created_count, updated_count, error_count


def import_bosa_raw_files(raw_paths: list[Path], db_url: str | None = None) -> tuple[int, int, int]:
    """Import one or more BOSA raw JSON files. Returns (imported_new, imported_updated, errors)."""
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

    parser = argparse.ArgumentParser(description="Import raw BOSA e-Procurement JSON into the database")
    parser.add_argument("paths", nargs="+", help="Path(s) to raw BOSA JSON file(s)")
    parser.add_argument("--db-url", help="Optional DATABASE_URL override")
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    imported_new, imported_updated, errors = import_bosa_raw_files(paths, db_url=args.db_url)
    summary = {"imported_new": imported_new, "imported_updated": imported_updated, "errors": errors}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
