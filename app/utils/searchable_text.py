"""Utility functions for building searchable text from notices."""
import json
from typing import Any, Optional

from app.db.models.notice import Notice
from app.db.models.notice_detail import NoticeDetail


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


def build_searchable_text(notice: Notice, notice_detail: Optional[NoticeDetail] = None) -> str:
    """
    Build searchable text from notice for keyword matching.
    Includes:
    - Notice.title
    - Raw JSON fields (notice-title, title-proc, title-glo, description-glo, description-proc) via pick_text()
    - Optional notice_details content if present
    """
    parts = []
    
    # Add notice title
    if notice.title:
        parts.append(notice.title)
    
    # Extract from raw_json if available
    if notice.raw_json:
        try:
            raw_data = json.loads(notice.raw_json)
            # Try various title fields
            for field in ("notice-title", "title-proc", "title-glo"):
                text = pick_text(raw_data.get(field))
                if text and text not in parts:
                    parts.append(text)
            # Try description fields
            for field in ("description-glo", "description-proc", "description"):
                text = pick_text(raw_data.get(field))
                if text and text not in parts:
                    parts.append(text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    
    # Extract from notice_detail if available
    if notice_detail and notice_detail.raw_json:
        try:
            detail_data = json.loads(notice_detail.raw_json)
            # Try various title fields
            for field in ("notice-title", "title-proc", "title-glo"):
                text = pick_text(detail_data.get(field))
                if text and text not in parts:
                    parts.append(text)
            # Try description fields
            for field in ("description-glo", "description-proc", "description"):
                text = pick_text(detail_data.get(field))
                if text and text not in parts:
                    parts.append(text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    
    # Join all parts with spaces
    return " ".join(parts).lower()
