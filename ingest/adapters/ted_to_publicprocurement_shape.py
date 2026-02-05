"""
Convert TED (Tenders Electronic Daily) raw JSON into the publications list shape
expected by ingest/import_publicprocurement.py (dossier, cpvMainCode, etc.).
Does not modify import_publicprocurement.py; import continues to use SOURCE_NAME.
"""
from typing import Any


def _extract_notice_id(notice: dict[str, Any]) -> str | None:
    """Get unique notice identifier from TED notice."""
    return (
        notice.get("noticeId")
        or notice.get("id")
        or notice.get("notice_id")
        or (notice.get("metadata", {}) or {}).get("noticeId")
    )


def _extract_title(notice: dict[str, Any]) -> str:
    """Get title; TED may have title (str) or titles (list of {language, value})."""
    title = notice.get("title")
    if isinstance(title, str) and title.strip():
        return title[:500]
    titles = notice.get("titles") or notice.get("titleList") or []
    for t in titles if isinstance(titles, list) else []:
        if isinstance(t, dict):
            text = t.get("value") or t.get("text") or ""
            if isinstance(text, str) and text.strip():
                return text[:500]
    return "Untitled"


def _extract_date(notice: dict[str, Any], *keys: str) -> str | None:
    """Get first non-empty date string from notice."""
    for key in keys:
        val = notice.get(key)
        if val and isinstance(val, str):
            return val
    return None


def _extract_cpv_main(notice: dict[str, Any]) -> str | None:
    """Get main CPV code; TED may use mainCpv, cpvCode, cpvCodes[0], etc."""
    main = notice.get("mainCpv") or notice.get("cpvCode") or notice.get("cpvMainCode")
    if isinstance(main, dict):
        return (main.get("code") or main.get("value") or "").strip() or None
    if isinstance(main, str) and main.strip():
        return main.strip()
    codes = notice.get("cpvCodes") or notice.get("cpv") or []
    if isinstance(codes, list) and codes:
        first = codes[0]
        if isinstance(first, dict):
            return (first.get("code") or first.get("value") or "").strip() or None
        if isinstance(first, str):
            return first.strip() or None
    return None


def _extract_cpv_additional(notice: dict[str, Any]) -> list[dict[str, str]]:
    """Get additional CPV codes as list of {code: ...}."""
    additional = notice.get("additionalCpvs") or notice.get("cpvAdditionalCodes") or []
    out = []
    for item in additional if isinstance(additional, list) else []:
        if isinstance(item, dict):
            code = (item.get("code") or item.get("value") or "").strip()
            if code:
                out.append({"code": code})
        elif isinstance(item, str) and item.strip():
            out.append({"code": item.strip()})
    return out


def _extract_buyer(notice: dict[str, Any]) -> dict[str, str] | None:
    """Get buyer/contracting authority as {name} or {legalName}."""
    authority = (
        notice.get("contractingAuthority")
        or notice.get("buyer")
        or notice.get("organisation")
        or notice.get("authority")
    )
    if isinstance(authority, dict):
        name = authority.get("name") or authority.get("legalName") or authority.get("officialName")
        if name:
            return {"name": str(name)[:255], "legalName": str(name)[:255]}
    if isinstance(authority, str) and authority.strip():
        return {"name": authority.strip()[:255], "legalName": authority.strip()[:255]}
    return None


def _extract_procedure_type(notice: dict[str, Any]) -> str | None:
    """Get procedure type."""
    pt = notice.get("procedureType") or notice.get("procurementProcedureType")
    if isinstance(pt, str) and pt.strip():
        return pt.strip()[:100]
    return None


def _extract_url(notice: dict[str, Any], notice_id: str | None) -> str:
    """Build TED notice URL."""
    url = notice.get("url") or notice.get("link") or notice.get("noticeUrl")
    if isinstance(url, str) and url.strip():
        return url.strip()[:1000]
    if notice_id:
        return f"https://ted.europa.eu/udl?uri=TED:NOTICE:{notice_id}"[:1000]
    return "https://ted.europa.eu"


def ted_notice_to_publication(notice: dict[str, Any]) -> dict[str, Any]:
    """
    Map a single TED notice to the publicprocurement.be publication shape
    expected by import_publicprocurement.py (dossier, cpvMainCode, etc.).
    """
    notice_id = _extract_notice_id(notice)
    title = _extract_title(notice)
    publication_date = _extract_date(
        notice, "publicationDate", "dispatchDate", "date", "insertionDate"
    )
    deadline_date = _extract_date(notice, "deadlineDate", "deadline", "submissionDeadline")
    cpv_main = _extract_cpv_main(notice)
    cpv_additional = _extract_cpv_additional(notice)
    buyer = _extract_buyer(notice)
    procedure_type = _extract_procedure_type(notice)
    url = _extract_url(notice, notice_id)

    # Shape expected by import_publicprocurement.py
    dossier: dict[str, Any] = {
        "referenceNumber": notice_id,
        "number": notice_id,
        "titles": [{"language": "EN", "text": title}],
        "procurementProcedureType": procedure_type,
    }
    pub: dict[str, Any] = {
        "id": notice_id,
        "dossier": dossier,
        "dispatchDate": publication_date,
        "insertionDate": publication_date,
        "deadlineDate": deadline_date,
        "shortlink": None,
        "noticeIds": [notice_id] if notice_id else [],
    }
    if buyer:
        pub["buyer"] = buyer
        dossier["buyer"] = buyer
    if cpv_main:
        pub["cpvMainCode"] = {"code": cpv_main}
    if cpv_additional:
        pub["cpvAdditionalCodes"] = cpv_additional
    # Import builds URL from shortlink (prepends publicprocurement.be) or noticeIds; we do not
    # set shortlink so URL will point to publicprocurement.be. Correct TED URL would require
    # importer support (not changed here).
    return pub


def ted_result_to_publications_shape(ted_result: dict[str, Any]) -> dict[str, Any]:
    """
    Convert full TED search result (normalized shape with metadata + json)
    into import-ready shape: { metadata, json: { publications: [...] } }.
    """
    metadata = ted_result.get("metadata", {})
    raw_json = ted_result.get("json", ted_result)
    # TED may return notices in different keys
    notices = (
        raw_json.get("notices")
        or raw_json.get("results")
        or raw_json.get("items")
        or raw_json.get("data")
        or []
    )
    if not isinstance(notices, list):
        notices = []

    publications = [ted_notice_to_publication(n) for n in notices if isinstance(n, dict)]
    return {
        "metadata": metadata,
        "json": {
            "publications": publications,
        },
    }
