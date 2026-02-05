"""
Extract lots and documents from publication detail JSON.
Media API / partner API shapes may vary; we use flexible paths and return normalized dicts.
"""
from datetime import datetime
from typing import Any, Optional


def extract_lots(detail_json: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract lots from publication detail JSON.
    Returns list of dicts with keys: lot_number, title, description, cpv_code, nuts_code (all optional strings).
    """
    result: list[dict[str, Any]] = []
    if not isinstance(detail_json, dict):
        return result
    dossier = detail_json.get("dossier") or detail_json.get("publication") or {}
    raw_lots = (
        dossier.get("lots")
        or dossier.get("divisions")
        or detail_json.get("lots")
        or detail_json.get("divisions")
        or []
    )
    if not isinstance(raw_lots, list):
        return result
    for idx, item in enumerate(raw_lots):
        if not isinstance(item, dict):
            continue
        lot_number = _str(item.get("lotNumber") or item.get("number") or item.get("id") or (idx + 1))
        title = _str(item.get("title") or item.get("name"))
        description = _str(item.get("description") or item.get("descriptionText"))
        cpv = item.get("cpvCode") or item.get("cpv") or item.get("cpvCodeMain")
        cpv_code = _str(cpv.get("code") if isinstance(cpv, dict) else cpv)
        nuts = item.get("nutsCode") or item.get("nuts") or item.get("placeOfPerformance")
        nuts_code = _str(nuts.get("code") if isinstance(nuts, dict) else nuts)
        result.append({
            "lot_number": lot_number or None,
            "title": title or None,
            "description": description or None,
            "cpv_code": cpv_code or None,
            "nuts_code": nuts_code or None,
        })
    return result


def extract_documents(detail_json: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract documents from publication detail JSON.
    Returns list of dicts with keys: lot_number (optional, for linking), title, url, file_type, language,
    published_at (iso string or None), checksum (optional).
    """
    result: list[dict[str, Any]] = []
    if not isinstance(detail_json, dict):
        return result
    dossier = detail_json.get("dossier") or detail_json.get("publication") or {}
    raw_docs = (
        dossier.get("documents")
        or dossier.get("attachments")
        or detail_json.get("documents")
        or detail_json.get("attachments")
        or []
    )
    if not isinstance(raw_docs, list):
        return result
    for item in raw_docs:
        if not isinstance(item, dict):
            continue
        url = _str(item.get("url") or item.get("link") or item.get("href") or item.get("documentUrl"))
        if not url:
            continue
        title = _str(item.get("title") or item.get("name") or item.get("fileName"))
        file_type = _str(item.get("fileType") or item.get("type") or item.get("mimeType"))
        language = _str(item.get("language") or item.get("lang"))
        published_at = _parse_datetime(item.get("publishedAt") or item.get("publicationDate") or item.get("date"))
        checksum = _str(item.get("checksum") or item.get("hash") or item.get("md5"))
        lot_number = _str(item.get("lotNumber") or item.get("lotId") or (item.get("lot") or {}).get("number") if isinstance(item.get("lot"), dict) else None)
        result.append({
            "lot_number": lot_number or None,
            "title": title or None,
            "url": url,
            "file_type": file_type or None,
            "language": language or None,
            "published_at": published_at,
            "checksum": checksum or None,
        })
    return result


def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _parse_datetime(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        if s:
            return s
    return None
