"""Service for importing BOSA and TED procurement notices into the database."""
import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.connectors.eproc_connector import fetch_publication_workspace
from app.connectors.ted_connector import search_ted_notices as search_ted_notices_app
from app.models.notice_cpv_additional import NoticeCpvAdditional
from app.models.notice_lot import NoticeLot
from app.connectors.bosa.client import search_publications as search_publications_bosa
from app.models.notice import NoticeSource, ProcurementNotice

logger = logging.getLogger(__name__)

BOSA_SOURCE = NoticeSource.BOSA_EPROC.value
TED_SOURCE = NoticeSource.TED_EU.value


def _safe_str(value: Any, max_len: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip() or None
    if s and max_len is not None:
        s = s[:max_len]
    return s


def _safe_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    try:
        s = str(value).strip()
        if not s:
            return None
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _safe_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value).strip()
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def _safe_json_list(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    return None


def _safe_json_dict(value: Any) -> Optional[dict[str, str]]:
    if value is None or not isinstance(value, dict):
        return None
    return {str(k): str(v) for k, v in value.items() if v is not None and str(v).strip()}


def _get_nested(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Get value by dotted path, e.g. 'organisation.organisationNames' or 'dossier.referenceNumber'."""
    if not data or not path:
        return default
    parts = path.split(".")
    cur = data
    for p in parts:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def _get_from_sources(item: dict[str, Any], workspace: Optional[dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """Try each key in workspace first, then item. Keys can be dotted for nested (e.g. 'cpvMainCode.code')."""
    for key in keys:
        for source in (workspace, item):
            if not source:
                continue
            v = _get_nested(source, key) if "." in key else source.get(key) or source.get(key.replace("_", ""))
            if v is not None:
                return v
    return default


def _extract_cpv_main_code(item: dict[str, Any], workspace: Optional[dict[str, Any]]) -> Optional[str]:
    """Extract main CPV code: API returns cpvMainCode as object { code: '45000000-7' } or string."""
    raw = _get_from_sources(item, workspace, "cpvMainCode.code", "cpvMainCode", "cpv_main_code", "mainCpvCode", "cpvCode", "cpv")
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("code") or raw.get("id")
    return _safe_str(raw, 20) if raw else None


def _extract_cpv_additional_codes(item: dict[str, Any], workspace: Optional[dict[str, Any]]) -> Optional[list[str]]:
    """Extract additional CPV codes: API returns list of { code: '...' }."""
    raw = _get_from_sources(item, workspace, "cpvAdditionalCodes", "cpv_additional_codes", "additionalCpvCodes")
    if not isinstance(raw, list):
        return None
    codes = []
    for entry in raw:
        if isinstance(entry, dict):
            c = entry.get("code") or entry.get("id")
            if c and str(c).strip():
                codes.append(str(c).strip())
        elif entry is not None and str(entry).strip():
            codes.append(str(entry).strip())
    return codes if codes else None


def _extract_organisation_names(item: dict[str, Any], workspace: Optional[dict[str, Any]]) -> Optional[dict[str, str]]:
    """Extract organisation names: API has organisation.organisationNames as [ { language: 'FR', text: '...' } ] or organisation.names."""
    raw = _get_from_sources(
        item, workspace,
        "organisation.organisationNames", "organisation.organisation_names",
        "organisation.names", "organisationNames", "organisation_names",
        "contractingAuthority", "buyerName",
    )
    if isinstance(raw, dict) and not any(isinstance(v, (list, dict)) for v in raw.values()):
        return _safe_json_dict(raw)
    if isinstance(raw, str):
        return {"default": raw.strip()} if raw.strip() else None
    if isinstance(raw, list):
        out = {}
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            lang = (entry.get("language") or entry.get("lang") or "default")
            if isinstance(lang, str):
                lang = lang.upper()[:2]
            text = entry.get("text") or entry.get("name") or entry.get("value")
            if text is not None and str(text).strip():
                out[lang] = str(text).strip()
        return out if out else None
    return None


def _extract_title(item: dict[str, Any], workspace: Optional[dict[str, Any]]) -> Optional[str]:
    """Extract title from dossier.titles[0].text, title, or name."""
    raw = _get_from_sources(item, workspace, "dossier.titles", "title", "name", "titles")
    if isinstance(raw, list) and len(raw) > 0:
        first = raw[0]
        if isinstance(first, dict):
            t = first.get("text") or first.get("name") or first.get("value")
            if t:
                return _safe_str(t, 1000)
    if isinstance(raw, str):
        return _safe_str(raw, 1000)
    return _safe_str(_get_from_sources(item, workspace, "title", "name"), 1000)


def _bosa_extract_lots(publication: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract lots from BOSA publication (workspace). Each lot: number, title, external_id, status."""
    lots_data = publication.get("lots") or publication.get("lotsData") or []
    lots = []
    for lot in lots_data if isinstance(lots_data, list) else []:
        if not isinstance(lot, dict):
            continue
        titles = lot.get("titles") or lot.get("title") or []
        if not isinstance(titles, list):
            titles = [{"text": str(titles), "language": "FR"}] if titles else []
        title = None
        for t in titles:
            if isinstance(t, dict) and t.get("language") == "FR":
                title = (t.get("text") or t.get("value") or "").strip()
                break
        if not title and titles:
            first = titles[0]
            title = (first.get("text") or first.get("value") or str(first)).strip() if isinstance(first, dict) else str(first)
        if not title:
            title = f"Lot {lot.get('number', '?')}"
        lots.append({
            "number": _safe_str(lot.get("number") or lot.get("lotNumber"), 50),
            "title": _safe_str(title, 500),
            "external_id": _safe_str(lot.get("id"), 255),
            "status": _safe_str(lot.get("status") or "ACTIVE", 50),
        })
    return lots


def _bosa_enrich_raw_data_and_extras(
    publication: dict[str, Any],
    source_id: str,
    cpv_main_code: Optional[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """
    Build enriched raw_data (url, status, certificates, dossier, agreement, keywords, etc.)
    and extract lots + additional CPV codes for persistence.
    Returns (enriched_raw_data, lots_for_notice_lots, additional_cpv_codes).
    """
    raw = dict(publication) if publication else {}

    # URL (constructible)
    pub_id = publication.get("id") if publication else None
    if pub_id:
        raw["url"] = f"https://publicprocurement.be/publication-workspaces/{pub_id}/general"

    # Status & lifecycle
    raw["status"] = publication.get("status", "PUBLISHED") if publication else "PUBLISHED"
    raw["agreement_status"] = publication.get("agreementStatus") if publication else None
    raw["dossier_status"] = publication.get("dossierStatus") if publication else None
    raw["cancelled_at"] = publication.get("cancelledAt") if publication else None
    raw["migrated"] = publication.get("migrated", False) if publication else False

    # Certificates (required_accreditation)
    certificates = (publication or {}).get("certificates") or []
    if certificates:
        cert_descriptions = []
        for cert in certificates if isinstance(certificates, list) else []:
            if isinstance(cert, dict):
                d = cert.get("description") or cert.get("type")
                if d:
                    cert_descriptions.append(str(d))
        if cert_descriptions:
            raw["required_accreditation"] = ", ".join(cert_descriptions)

    # Dossier info
    dossier = (publication or {}).get("dossier") or {}
    if dossier:
        dossier_titles = dossier.get("titles") or []
        dossier_title = None
        for t in dossier_titles if isinstance(dossier_titles, list) else []:
            if isinstance(t, dict) and t.get("language") == "FR":
                dossier_title = (t.get("text") or t.get("value") or "").strip()
                break
        if not dossier_title and dossier_titles:
            first = dossier_titles[0]
            dossier_title = (first.get("text") or first.get("value") or "").strip() if isinstance(first, dict) else ""
        raw["dossier_id"] = dossier.get("id")
        raw["dossier_number"] = dossier.get("number")
        raw["dossier_title"] = dossier_title

    # Agreement
    raw["agreement_id"] = (publication or {}).get("agreementId")

    # Organisation (FR name)
    org = (publication or {}).get("organisation") or {}
    org_names = org.get("organisationNames") or org.get("organisation_names") or []
    org_name_fr = None
    for n in org_names if isinstance(org_names, list) else []:
        if isinstance(n, dict) and n.get("language") == "FR":
            org_name_fr = (n.get("text") or n.get("value") or "").strip()
            break
    if not org_name_fr and org_names:
        first = org_names[0]
        org_name_fr = (first.get("text") or first.get("value") or "").strip() if isinstance(first, dict) else None
    raw["organisation_name"] = org_name_fr
    raw["organisation_id"] = org.get("organisationId") or org.get("id")

    # All CPV codes (for raw_data and for notice_cpv_additional)
    all_cpv = (publication or {}).get("allCpvCodes") or []
    agreement_cpv = (publication or {}).get("agreementCpvCodes") or []
    if not isinstance(all_cpv, list):
        all_cpv = []
    if not isinstance(agreement_cpv, list):
        agreement_cpv = []
    def _cpv_code(c: Any) -> Optional[str]:
        if isinstance(c, str) and c.strip():
            return c.strip()
        if isinstance(c, dict):
            return (c.get("code") or c.get("id") or "").strip() or None
        return None
    raw["all_cpv_codes"] = [_cpv_code(c) for c in all_cpv if _cpv_code(c)]
    raw["agreement_cpv_codes"] = [_cpv_code(c) for c in agreement_cpv if _cpv_code(c)]
    # Additional CPV: all codes except main (for notice_cpv_additional table)
    main_normalized = (cpv_main_code or "").replace("-", "").strip()[:8] if cpv_main_code else None
    additional_cpv_codes = []
    for c in raw["all_cpv_codes"]:
        code = (c or "").replace("-", "").strip()[:8]
        if code and code != main_normalized:
            additional_cpv_codes.append(c if isinstance(c, str) else str(c))

    # Keywords (FR)
    keywords = (publication or {}).get("keywords") or []
    keywords_fr = []
    for kw in keywords if isinstance(keywords, list) else []:
        if isinstance(kw, dict) and kw.get("language") == "FR":
            t = kw.get("text") or kw.get("value")
            if t:
                keywords_fr.append(str(t).strip())
    raw["keywords"] = keywords_fr

    # Lots for notice_lots table
    lots = _bosa_extract_lots(publication or {})

    return raw, lots, additional_cpv_codes


def _extract_bosa_description(
    item: dict[str, Any], workspace: Optional[dict[str, Any]]
) -> Optional[str]:
    """Extract description from BOSA dossier.descriptions multilingual array."""
    for source in (workspace, item) if workspace else (item,):
        if not isinstance(source, dict):
            continue
        dossier = source.get("dossier")
        if isinstance(dossier, dict):
            descs = dossier.get("descriptions")
            if isinstance(descs, list) and descs:
                for pref_lang in ("FR", "NL", "EN", "DE"):
                    for entry in descs:
                        if isinstance(entry, dict) and str(entry.get("language", "")).upper() == pref_lang:
                            t = str(entry.get("text", "")).strip()
                            if t:
                                return t[:10000]
                # Fallback: first available
                for entry in descs:
                    if isinstance(entry, dict):
                        t = str(entry.get("text", "")).strip()
                        if t:
                            return t[:10000]
    # Final fallback: top-level description/summary
    desc = _get_from_sources(item, workspace, "description", "summary")
    return _safe_str(desc, 10000) if desc else None


def _map_search_item_to_notice(
    item: dict[str, Any],
    workspace: Optional[dict[str, Any]],
    source_id: str,
) -> dict[str, Any]:
    """Build kwargs for ProcurementNotice from search item and optional workspace detail.
    Uses workspace when present and falls back to item for each field.
    Enriches raw_data with BOSA full API fields; adds _bosa_lots and _bosa_additional_cpv for persistence.
    """
    publication = workspace if workspace else item

    def get(*keys: str, default=None):
        return _get_from_sources(item, workspace, *keys, default=default)

    # CPV: main (object with .code in API) and additional (list of { code })
    cpv_main_code = _extract_cpv_main_code(item, workspace)
    cpv_additional_codes = _extract_cpv_additional_codes(item, workspace)

    # Enrich raw_data and get lots + additional CPV for DB
    enriched_raw, bosa_lots, bosa_additional_cpv = _bosa_enrich_raw_data_and_extras(
        publication, source_id, cpv_main_code
    )
    # If we had no workspace, additional_cpv from API might not be in allCpvCodes; keep merge with existing
    if cpv_additional_codes and not bosa_additional_cpv:
        bosa_additional_cpv = list(cpv_additional_codes)

    # NUTS: list of strings
    nuts = get("nutsCodes", "nuts_codes", "nutsCode")
    nuts_codes = _safe_json_list(nuts) if nuts else None

    # Organisation names: organisation.organisationNames as [ { language, text } ]
    organisation_names = _extract_organisation_names(item, workspace)

    # Organisation id: top-level or organisation.organisationId
    organisation_id = _safe_str(
        get("organisation.organisationId", "organisationId", "organisation_id"),
        255,
    )
    if organisation_id is None:
        org = _get_from_sources(item, workspace, "organisation")
        if isinstance(org, dict):
            organisation_id = _safe_str(org.get("organisationId") or org.get("id"), 255)

    # Publication languages
    pub_lang = get("publicationLanguages", "publication_languages", "language")
    publication_languages = _safe_json_list(pub_lang) if pub_lang else None

    # Reference number: top-level or dossier.referenceNumber
    reference_number = _safe_str(
        get("referenceNumber", "reference_number", "dossier.referenceNumber", "dossier.number"),
        255,
    )

    # Title from dossier.titles or top-level
    title = _extract_title(item, workspace)

    # Deadline: vaultSubmissionDeadline or submissionDeadline
    deadline = _safe_datetime(
        get("vaultSubmissionDeadline", "submissionDeadline", "submission_deadline", "deadline"),
    )

    # BOSA enriched columns (from enriched_raw)
    return {
        "source_id": source_id,
        "source": BOSA_SOURCE,
        "publication_workspace_id": source_id,
        "procedure_id": _safe_str(get("procedureId", "procedure_id"), 255),
        "dossier_id": _safe_str(get("dossierId", "dossier_id"), 255),
        "reference_number": reference_number,
        "cpv_main_code": cpv_main_code,
        "cpv_additional_codes": cpv_additional_codes,
        "nuts_codes": nuts_codes,
        "publication_date": _safe_date(get("publicationDate", "publication_date")),
        "insertion_date": _safe_datetime(get("insertionDate", "insertion_date")),
        "notice_type": _safe_str(get("publicationType", "noticeType", "notice_type"), 100),
        "notice_sub_type": _safe_str(get("noticeSubType", "notice_sub_type"), 100),
        "form_type": _safe_str(get("noticeSubType", "formType", "form_type"), 100),
        "organisation_id": organisation_id,
        "organisation_names": organisation_names,
        "publication_languages": publication_languages,
        "raw_data": enriched_raw,
        "title": title,
        "description": _extract_bosa_description(item, workspace),
        "deadline": deadline,
        "estimated_value": _safe_decimal(get("estimatedValue", "estimated_value", "value")),
        "url": _safe_str(enriched_raw.get("url"), 1000),
        "status": _safe_str(enriched_raw.get("status"), 50),
        "agreement_status": _safe_str(enriched_raw.get("agreement_status"), 100),
        "dossier_status": _safe_str(enriched_raw.get("dossier_status"), 100),
        "cancelled_at": _safe_datetime(enriched_raw.get("cancelled_at")),
        "required_accreditation": _safe_str(enriched_raw.get("required_accreditation"), 500),
        "dossier_number": _safe_str(enriched_raw.get("dossier_number"), 255),
        "dossier_title": _safe_str(enriched_raw.get("dossier_title"), None),
        "agreement_id": _safe_str(enriched_raw.get("agreement_id"), 255),
        "keywords": enriched_raw.get("keywords") if isinstance(enriched_raw.get("keywords"), list) else None,
        "migrated": bool(enriched_raw.get("migrated", False)),
        "_bosa_lots": bosa_lots,
        "_bosa_additional_cpv": bosa_additional_cpv,
    }


def _ted_pick_text(value: Any) -> Optional[str]:
    """Extract text from TED multi-language value (str, or dict with eng/fra/...)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for lang in ("eng", "ENG", "fra", "FRA", "en", "EN", "fr", "FR"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _generate_ted_url_from_item(item: dict[str, Any]) -> Optional[str]:
    """Generate TED notice URL from links field or publication-number."""
    # Check links field first (direct URL from API)
    links = item.get("links")
    if isinstance(links, dict):
        for key in ("html", "xml", "pdf"):
            url = links.get(key)
            if isinstance(url, str) and url.strip():
                return url.strip()
    elif isinstance(links, list) and links:
        first = links[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        elif isinstance(first, dict):
            url = first.get("url") or first.get("href")
            if isinstance(url, str) and url.strip():
                return url.strip()

    # Check document-url-lot (per-lot document links)
    doc_url = item.get("document-url-lot")
    if isinstance(doc_url, str) and doc_url.strip():
        return doc_url.strip()
    elif isinstance(doc_url, list) and doc_url:
        first = doc_url[0]
        if isinstance(first, str) and first.strip():
            return first.strip()

    # Fallback: generate from publication-number
    pub_number = item.get("publication-number") or item.get("publicationNumber")
    if pub_number and str(pub_number).strip():
        return f"https://ted.europa.eu/en/notice/-/detail/{str(pub_number).strip()}"
    return None


def _extract_ted_organisation_names(item: dict[str, Any]) -> Optional[dict[str, str]]:
    """
    Extract organisation_names from TED notice.
    Handles buyer-name as: string; or dict of lang -> list/str (e.g. {"deu": ["ÖBB-Infrastruktur AG"], "eng": ["Name"]}).
    Prefer EN, FR, then first available. List values: use first element.
    """
    buyer_name = item.get("buyer-name")
    if isinstance(buyer_name, str) and buyer_name.strip():
        return {"default": buyer_name.strip()[:255]}
    if isinstance(buyer_name, dict) and buyer_name:
        def _first_text(v: Any) -> Optional[str]:
            if isinstance(v, list) and v:
                v = v[0]
            return str(v).strip()[:255] if isinstance(v, str) and v.strip() else None

        out: dict[str, str] = {}
        preferred = ("eng", "ENG", "fra", "FRA", "en", "EN", "fr", "FR", "deu", "DEU")
        for lang in preferred:
            val = buyer_name.get(lang)
            text = _first_text(val) if val is not None else None
            if text:
                out[lang.lower()[:3]] = text
        if not out:
            for k, v in buyer_name.items():
                text = _first_text(v)
                if text:
                    out[str(k).lower()[:3]] = text
                    break
        return out if out else None
    authority = (
        item.get("contractingAuthority")
        or item.get("buyer")
        or item.get("organisation")
        or item.get("authority")
    )
    if isinstance(authority, dict):
        name = authority.get("name") or authority.get("legalName") or authority.get("officialName")
        if name and str(name).strip():
            return {"default": str(name).strip()[:255]}
    elif isinstance(authority, str) and authority.strip():
        return {"default": authority.strip()[:255]}
    return None


def _ted_source_id(item: dict[str, Any]) -> Optional[str]:
    """TED stable identifier: publication-number then noticeId."""
    pub = item.get("publication-number")
    if isinstance(pub, str) and pub.strip():
        return pub.strip()
    raw = item.get("noticeId") or item.get("id") or item.get("notice_id")
    if raw is not None:
        return str(raw).strip() or None
    meta = item.get("metadata")
    if isinstance(meta, dict):
        raw = meta.get("noticeId")
        if raw is not None:
            return str(raw).strip() or None
    return None


def _map_ted_item_to_notice(item: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Build kwargs for ProcurementNotice from a TED search result item."""
    # Title: notice-title (may be multi-lang dict), title-proc, title-glo, title
    title = _ted_pick_text(item.get("notice-title"))
    if not title:
        title = (
            _ted_pick_text(item.get("title-lot"))
            or _ted_pick_text(item.get("title-proc"))
            or _ted_pick_text(item.get("title-glo"))
            or item.get("title")
        )
    title = _safe_str(title, 1000) if title else None

    # Main CPV: main-classification-proc (TED Search API), or mainCpv, cpvCode, classification-cpv
    cpv_raw = (
        item.get("main-classification-proc")
        or item.get("mainCpv")
        or item.get("cpvCode")
        or item.get("cpvMainCode")
        or item.get("classification-cpv")
    )
    cpv_main_code = None
    if isinstance(cpv_raw, dict):
        cpv_main_code = _safe_str(cpv_raw.get("code") or cpv_raw.get("id") or cpv_raw.get("value"), 20)
    elif cpv_raw is not None and str(cpv_raw).strip():
        cpv_main_code = _safe_str(str(cpv_raw).strip(), 20)

    # Additional CPV codes
    cpv_additional_codes = None
    for key in ("classification-cpv", "additionalCpvs", "cpvAdditionalCodes", "classification-cpv-additional"):
        raw = item.get(key)
        if isinstance(raw, list):
            codes = []
            for entry in raw:
                if isinstance(entry, dict):
                    c = entry.get("code") or entry.get("id") or entry.get("value")
                    if c and str(c).strip():
                        codes.append(str(c).strip())
                elif entry is not None and str(entry).strip():
                    codes.append(str(entry).strip())
            if codes:
                cpv_additional_codes = codes
                break

    # Organisation: buyer-name (string, or dict of lang -> list/str), or contractingAuthority / buyer / organisation
    organisation_names = _extract_ted_organisation_names(item)

    # Dates
    pub_date = item.get("publication-date") or item.get("publicationDate")
    publication_date = _safe_date(pub_date)
    deadline_val = (
        item.get("deadline-receipt-tender-date-lot")
        or item.get("deadline-date-lot")
        or item.get("deadline-receipt-tender")
        or item.get("deadlineDate")
        or item.get("deadline")
        or item.get("submissionDeadline")
    )
    deadline = _safe_datetime(deadline_val)

    # Procedure type / form
    procedure_type = _safe_str(
        item.get("procedure-type") or item.get("procedureType") or item.get("procurementProcedureType"),
        100,
    )
    form_type = _safe_str(item.get("form-type") or item.get("formType"), 100)

    return {
        "source_id": source_id,
        "source": TED_SOURCE,
        "publication_workspace_id": source_id,
        "procedure_id": _safe_str(item.get("procedureId") or item.get("procedure-id"), 255),
        "dossier_id": _safe_str(item.get("dossierId") or item.get("dossier-id"), 255),
        "reference_number": _safe_str(item.get("referenceNumber") or item.get("reference-number"), 255),
        "cpv_main_code": cpv_main_code,
        "cpv_additional_codes": cpv_additional_codes,
        "nuts_codes": _safe_json_list(
            item.get("place-of-performance")
            or item.get("place-of-performance-country-lot")
            or item.get("nutsCodes")
            or item.get("nutsCode")
        ),
        "publication_date": publication_date,
        "insertion_date": _safe_datetime(item.get("insertionDate") or item.get("insertion-date")),
        "notice_type": _safe_str(
            item.get("notice-type")
            or item.get("contract-nature-main-proc")
            or item.get("noticeType")
            or item.get("procedure-type"),
            100,
        ),
        "notice_sub_type": _safe_str(item.get("notice-subtype") or item.get("noticeSubType") or item.get("notice-sub-type"), 100),
        "form_type": form_type,
        "organisation_id": _safe_str(item.get("organisationId") or item.get("organisation-id"), 255),
        "organisation_names": organisation_names,
        "publication_languages": _safe_json_list(item.get("publicationLanguages") or item.get("language")),
        "raw_data": item,
        "title": title,
        "description": _safe_str(
            _ted_pick_text(item.get("description-lot"))
            or _ted_pick_text(item.get("description-glo"))
            or _ted_pick_text(item.get("description-proc"))
            or _ted_pick_text(item.get("additional-information-lot"))
            or item.get("description")
            or item.get("summary")
        ),
        "deadline": deadline,
        "estimated_value": _safe_decimal(
            item.get("estimated-value-lot")
            or item.get("framework-estimated-value-glo")
            or item.get("estimatedValue")
            or item.get("estimated-value")
            or item.get("value")
        ),
        "url": _generate_ted_url_from_item(item),
    }


class NoticeService:
    """Import and manage BOSA procurement notices."""

    def __init__(self, db: Session):
        self.db = db

    async def import_from_eproc_search(
        self,
        search_results: list[dict],
        fetch_details: bool = True,
    ) -> dict[str, Any]:
        """
        Import notices from e-Procurement search results.

        Args:
            search_results: List of items from search API (e.g. publications list).
            fetch_details: If True, fetch full workspace details for each item.

        Returns:
            {"created": int, "updated": int, "skipped": int, "errors": list}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        for item in search_results:
            workspace_id = None
            raw = item if isinstance(item, dict) else None
            if raw:
                wid = raw.get("publicationWorkspaceId")
                if wid and isinstance(wid, str):
                    workspace_id = wid.strip()
            if not workspace_id:
                stats["skipped"] += 1
                continue

            try:
                # Fetch workspace detail first (needed for dossier_id dedup)
                workspace: Optional[dict[str, Any]] = None
                if fetch_details:
                    workspace = await asyncio.to_thread(
                        fetch_publication_workspace,
                        workspace_id,
                    )

                attrs = _map_search_item_to_notice(raw, workspace, workspace_id)
                bosa_lots = attrs.pop("_bosa_lots", [])
                bosa_additional_cpv = attrs.pop("_bosa_additional_cpv", [])

                # Dedup: prefer dossier_id (same tender, newer publication)
                # then fall back to source_id (exact same publication)
                existing = None
                dossier_id = attrs.get("dossier_id")
                if dossier_id:
                    existing = (
                        self.db.query(ProcurementNotice)
                        .filter(
                            ProcurementNotice.source == BOSA_SOURCE,
                            ProcurementNotice.dossier_id == dossier_id,
                        )
                        .first()
                    )
                if not existing:
                    existing = (
                        self.db.query(ProcurementNotice)
                        .filter(ProcurementNotice.source_id == workspace_id)
                        .first()
                    )

                if existing:
                    for key, value in attrs.items():
                        setattr(existing, key, value)
                    notice_entity = existing
                    stats["updated"] += 1
                    # Replace lots and additional CPV for this notice
                    self.db.query(NoticeLot).filter(NoticeLot.notice_id == existing.id).delete()
                    self.db.query(NoticeCpvAdditional).filter(NoticeCpvAdditional.notice_id == existing.id).delete()
                else:
                    notice = ProcurementNotice(**attrs)
                    self.db.add(notice)
                    self.db.flush()
                    notice_entity = notice
                    stats["created"] += 1

                notice_id = notice_entity.id
                for lot_data in bosa_lots:
                    if lot_data.get("number") is not None or lot_data.get("title"):
                        self.db.add(NoticeLot(
                            notice_id=notice_id,
                            lot_number=lot_data.get("number"),
                            title=lot_data.get("title"),
                            description=lot_data.get("external_id"),
                            cpv_code=None,
                            nuts_code=None,
                        ))
                for cpv_code in bosa_additional_cpv:
                    if cpv_code and str(cpv_code).strip():
                        self.db.add(NoticeCpvAdditional(
                            notice_id=notice_id,
                            cpv_code=str(cpv_code).strip()[:20],
                        ))
            except Exception as e:
                stats["errors"].append({"source_id": workspace_id, "message": str(e)})
                logger.warning("Import failed for %s: %s", workspace_id, e)
                continue

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            stats["errors"].append({"message": f"Commit failed: {e}"})
            logger.exception("Import commit failed")

        return stats

    async def import_from_ted_search(
        self,
        search_results: list[dict],
        fetch_details: bool = True,
    ) -> dict[str, Any]:
        """
        Import notices from TED search results.

        Args:
            search_results: List of TED notice objects (e.g. from search_ted_notices()["notices"]).
            fetch_details: Ignored for TED (no detail API in scope); kept for API consistency.

        Returns:
            {"created": int, "updated": int, "skipped": int, "errors": list}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        for item in search_results:
            raw = item if isinstance(item, dict) else None
            if not raw:
                stats["skipped"] += 1
                continue

            source_id = _ted_source_id(raw)
            if not source_id:
                stats["skipped"] += 1
                continue

            try:
                existing = (
                    self.db.query(ProcurementNotice)
                    .filter(ProcurementNotice.source_id == source_id)
                    .first()
                )
                attrs = _map_ted_item_to_notice(raw, source_id)

                if existing:
                    for key, value in attrs.items():
                        setattr(existing, key, value)
                    stats["updated"] += 1
                else:
                    notice = ProcurementNotice(**attrs)
                    self.db.add(notice)
                    stats["created"] += 1
            except Exception as e:
                stats["errors"].append({"source_id": source_id, "message": str(e)})
                logger.warning("TED import failed for %s: %s", source_id, e)
                continue

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            stats["errors"].append({"message": f"Commit failed: {e}"})
            logger.exception("TED import commit failed")

        return stats

    async def import_from_all_sources(
        self,
        search_criteria: dict[str, Any],
        fetch_details: bool = True,
        sources: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Run search against BOSA and/or TED in parallel, then import.
        One source failing does not block the other; errors are reported per source.

        Args:
            search_criteria: Unified criteria, e.g.:
                - term or keywords: search text
                - page: page number (default 1)
                - page_size: results per page (default 25)
                - cpv: optional CPV filter (may be used by connectors if supported)
            fetch_details: Passed to BOSA import; TED ignores it.
            sources: Optional list of "BOSA" and/or "TED"; if None or empty, run both.

        Returns:
            {"bosa": {created, updated, skipped, errors}, "ted": {...}, "total": {...}}
        """
        term = (search_criteria.get("term") or search_criteria.get("keywords") or "").strip()
        page = max(1, int(search_criteria.get("page", 1)))
        page_size = max(1, min(250, int(search_criteria.get("page_size", 25))))

        run_bosa_src = not sources or "BOSA" in [s.upper().strip() for s in sources if s]
        run_ted_src = not sources or "TED" in [s.upper().strip() for s in sources if s]

        bosa_result: Optional[dict[str, Any]] = None
        ted_result: Optional[dict[str, Any]] = None
        bosa_error: Optional[str] = None
        ted_error: Optional[str] = None

        async def run_bosa() -> None:
            nonlocal bosa_result, bosa_error
            if not run_bosa_src:
                return
            try:
                bosa_result = await asyncio.to_thread(
                    search_publications_bosa,
                    term=term,
                    page=page,
                    page_size=page_size,
                )
            except Exception as e:
                bosa_error = str(e)
                logger.exception("BOSA search failed")

        async def run_ted() -> None:
            nonlocal ted_result, ted_error
            if not run_ted_src:
                return
            try:
                ted_result = await asyncio.to_thread(
                    search_ted_notices_app,
                    term=term,
                    page=page,
                    page_size=page_size,
                )
            except Exception as e:
                ted_error = str(e)
                logger.exception("TED search failed")

        await asyncio.gather(run_bosa(), run_ted())

        bosa_stats: dict[str, Any] = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
        ted_stats: dict[str, Any] = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

        if run_bosa_src:
            if bosa_error:
                bosa_stats["errors"].append({"message": bosa_error})
            elif bosa_result is not None:
                payload = bosa_result.get("json") or {}
                bosa_items = []
                if isinstance(payload, dict):
                    for key in ("publications", "items", "results", "data"):
                        candidate = payload.get(key)
                        if isinstance(candidate, list):
                            bosa_items = candidate
                            break
                try:
                    bosa_stats = await self.import_from_eproc_search(bosa_items, fetch_details=fetch_details)
                except Exception as e:
                    bosa_stats["errors"].append({"message": str(e)})
                    logger.exception("BOSA import failed")

        if run_ted_src:
            if ted_error:
                ted_stats["errors"].append({"message": ted_error})
            elif ted_result is not None:
                ted_items = ted_result.get("notices") or (ted_result.get("json") or {}).get("notices") or []
                try:
                    ted_stats = await self.import_from_ted_search(ted_items, fetch_details=fetch_details)
                except Exception as e:
                    ted_stats["errors"].append({"message": str(e)})
                    logger.exception("TED import failed")

        total_created = bosa_stats["created"] + ted_stats["created"]
        total_updated = bosa_stats["updated"] + ted_stats["updated"]
        total_skipped = bosa_stats["skipped"] + ted_stats["skipped"]
        total_errors = list(bosa_stats["errors"]) + list(ted_stats["errors"])

        return {
            "bosa": bosa_stats,
            "ted": ted_stats,
            "total": {
                "created": total_created,
                "updated": total_updated,
                "skipped": total_skipped,
                "errors": total_errors,
            },
        }
