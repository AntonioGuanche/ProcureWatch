"""Utility functions for building searchable text from notices."""
import json
from typing import Any, Optional

from app.models.notice import Notice  # alias for ProcurementNotice
from app.models.notice_detail import NoticeDetail


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
        for lang in ("eng", "ENG", "fra", "FRA", "en", "EN", "fr", "FR"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
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


def build_searchable_text(
    notice: Notice, notice_detail: Optional[NoticeDetail] = None
) -> str:
    """
    Build searchable text from notice for keyword matching.
    Includes:
    - Notice.title and Notice.description
    - raw_data fields (notice-title, title-proc, description, keywords, etc.)
    - Optional notice_detail content if present
    """
    parts = []

    # Add notice title and description
    if notice.title:
        parts.append(notice.title)
    if notice.description:
        parts.append(notice.description)

    # Extract from raw_data (ProcurementNotice stores this as a JSON dict)
    raw_data = notice.raw_data
    if isinstance(raw_data, dict):
        for field in ("notice-title", "title-proc", "title-glo"):
            text = pick_text(raw_data.get(field))
            if text and text not in parts:
                parts.append(text)
        for field in (
            "description-glo",
            "description-proc",
            "description",
            "dossier_title",
            "organisation_name",
        ):
            text = pick_text(raw_data.get(field))
            if text and text not in parts:
                parts.append(text)
        # Include BOSA keywords if present
        keywords = raw_data.get("keywords")
        if isinstance(keywords, list):
            for kw in keywords:
                if isinstance(kw, str) and kw.strip():
                    parts.append(kw.strip())
    elif isinstance(raw_data, str) and raw_data.strip():
        # Fallback: try parsing as JSON string (legacy data)
        try:
            parsed = json.loads(raw_data)
            if isinstance(parsed, dict):
                for field in ("notice-title", "title-proc", "title-glo"):
                    text = pick_text(parsed.get(field))
                    if text and text not in parts:
                        parts.append(text)
                for field in (
                    "description-glo",
                    "description-proc",
                    "description",
                ):
                    text = pick_text(parsed.get(field))
                    if text and text not in parts:
                        parts.append(text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    # Extract from notice_detail if available
    if notice_detail and notice_detail.raw_json:
        try:
            detail_data = json.loads(notice_detail.raw_json)
            for field in ("notice-title", "title-proc", "title-glo"):
                text = pick_text(detail_data.get(field))
                if text and text not in parts:
                    parts.append(text)
            for field in (
                "description-glo",
                "description-proc",
                "description",
            ):
                text = pick_text(detail_data.get(field))
                if text and text not in parts:
                    parts.append(text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    return " ".join(parts).lower()
