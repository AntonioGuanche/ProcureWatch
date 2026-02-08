#!/usr/bin/env python3
"""Backfill CPV normalization for existing notices and notice_cpv_additional."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.notice import Notice
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.db.session import SessionLocal
from app.utils.cpv import normalize_cpv


def needs_normalization(s: str | None) -> bool:
    """True if value is not exactly 8 digits."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) != 8:
        return True
    return not s.isdigit()


def main() -> int:
    db = SessionLocal()
    notices_updated = 0
    additional_updated = 0

    try:
        notices = db.query(Notice).all()
        for notice in notices:
            updated = False
            raw_main = notice.cpv_main_code
            if raw_main and needs_normalization(raw_main):
                cpv_8, _, display = normalize_cpv(raw_main)
                if cpv_8:
                    notice.cpv_main_code = cpv_8
                    notice.cpv = display
                    updated = True
            if updated:
                notices_updated += 1

        db.commit()

        # notice_cpv_additional: column is cpv_code
        additional_rows = db.query(NoticeCpvAdditional).all()
        for row in additional_rows:
            raw = row.cpv_code
            if raw and needs_normalization(raw):
                cpv_8, _, _ = normalize_cpv(raw)
                if cpv_8:
                    row.cpv_code = cpv_8
                    additional_updated += 1

        db.commit()
        print(f"Notices updated: {notices_updated}")
        print(f"Notice CPV additional rows updated: {additional_updated}")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
