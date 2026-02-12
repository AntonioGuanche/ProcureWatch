"""Data enrichment service: backfill missing fields from existing raw_data.

Re-extracts fields from raw_data stored in notices table without making
any external API calls. Useful after schema/extraction improvements.
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text, func, case, cast, String
from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice as Notice, NoticeSource

logger = logging.getLogger(__name__)


# ── TED URL generation ──────────────────────────────────────────────

def _generate_ted_url(notice: Notice) -> Optional[str]:
    """Generate TED notice URL from raw_data links, document-url-lot, or source_id."""
    raw = notice.raw_data
    if isinstance(raw, dict):
        # Try links field
        links = raw.get("links")
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
        # Try document-url-lot
        doc_url = raw.get("document-url-lot")
        if isinstance(doc_url, str) and doc_url.strip():
            return doc_url.strip()
        elif isinstance(doc_url, list) and doc_url:
            first = doc_url[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
    # Fallback: generate from source_id (publication-number)
    pub_num = notice.source_id
    if not pub_num:
        return None
    pub_num = pub_num.strip()
    if pub_num:
        return f"https://ted.europa.eu/en/notice/-/detail/{pub_num}"
    return None


def _generate_bosa_url(notice: Notice) -> Optional[str]:
    """Generate BOSA notice URL from workspace ID.
    Format: https://publicprocurement.be/publication-workspaces/{workspace_id}/general
    """
    ws_id = notice.publication_workspace_id or notice.source_id
    if not ws_id:
        return None
    return f"https://publicprocurement.be/publication-workspaces/{ws_id.strip()}/general"


# ── Text extraction helpers ──────────────────────────────────────────

def _pick_text(value: Any) -> Optional[str]:
    """Extract text from multilingual dict, list, or string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for lang in ("fra", "FRA", "fr", "FR", "eng", "ENG", "en", "EN",
                      "nld", "NLD", "nl", "NL", "deu", "DEU", "de", "DE"):
            t = value.get(lang)
            if isinstance(t, list) and t:
                t = t[0]
            if isinstance(t, str) and t.strip():
                return t.strip()
        for v in value.values():
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, str) and v.strip():
                return v.strip()
    if isinstance(value, list):
        for v in value:
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _safe_str(value: Any, max_len: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len] if max_len else s


# ── TED enrichment from raw_data ─────────────────────────────────────

def _enrich_ted_notice(notice: Notice) -> dict[str, bool]:
    """Re-extract fields from TED raw_data. Returns dict of field: was_updated."""
    raw = notice.raw_data
    if not isinstance(raw, dict):
        return {}

    updated = {}

    # Description
    if not notice.description:
        desc = (
            _pick_text(raw.get("description-lot"))
            or _pick_text(raw.get("description-glo"))
            or _pick_text(raw.get("description-proc"))
            or _pick_text(raw.get("description-part"))
            or _pick_text(raw.get("additional-information-lot"))
            or _pick_text(raw.get("description"))
            or _pick_text(raw.get("summary"))
            or _pick_text(raw.get("short-description"))
        )
        if desc:
            notice.description = desc[:10000]
            updated["description"] = True

    # Notice type: contract-nature-main-proc is the confirmed TED field
    if not notice.notice_type:
        nt = (
            raw.get("contract-nature-main-proc")
            or raw.get("procedure-type")
            or raw.get("notice-type")
            or raw.get("noticeType")
            or raw.get("type-of-notice")
            or raw.get("document-type")
        )
        if nt:
            notice.notice_type = _safe_str(nt, 100)
            updated["notice_type"] = True

    # Form type
    if not notice.form_type:
        ft = raw.get("form-type") or raw.get("formType") or raw.get("document-form-type")
        if ft:
            notice.form_type = _safe_str(ft, 100)
            updated["form_type"] = True

    # NUTS codes
    if not notice.nuts_codes:
        nuts = (
            raw.get("place-of-performance-country-proc")
            or raw.get("place-of-performance")
            or raw.get("place-of-performance-country-lot")
            or raw.get("nutsCodes")
            or raw.get("nutsCode")
            or raw.get("nuts-code")
        )
        if nuts:
            if isinstance(nuts, str):
                notice.nuts_codes = [nuts.strip()]
                updated["nuts_codes"] = True
            elif isinstance(nuts, list):
                codes = []
                for n in nuts:
                    if isinstance(n, str) and n.strip():
                        codes.append(n.strip())
                    elif isinstance(n, dict):
                        c = n.get("code") or n.get("id")
                        if c:
                            codes.append(str(c).strip())
                if codes:
                    notice.nuts_codes = codes
                    updated["nuts_codes"] = True

    # Organisation names
    if not notice.organisation_names:
        buyer = raw.get("buyer-name")
        if isinstance(buyer, str) and buyer.strip():
            notice.organisation_names = {"default": buyer.strip()[:255]}
            updated["organisation_names"] = True
        elif isinstance(buyer, dict) and buyer:
            names = {}
            for lang in ("eng", "fra", "nld", "deu"):
                v = buyer.get(lang)
                if isinstance(v, list) and v:
                    v = v[0]
                if isinstance(v, str) and v.strip():
                    names[lang] = v.strip()[:255]
            if not names:
                for k, v in buyer.items():
                    if isinstance(v, list) and v:
                        v = v[0]
                    if isinstance(v, str) and v.strip():
                        names[k[:3].lower()] = v.strip()[:255]
                        break
            if names:
                notice.organisation_names = names
                updated["organisation_names"] = True
        # Fallback: buyer-city, contracting authority
        if not notice.organisation_names:
            for key in ("buyer-city", "contracting-authority", "authority"):
                val = _pick_text(raw.get(key))
                if val:
                    notice.organisation_names = {"default": val[:255]}
                    updated["organisation_names"] = True
                    break

    # URL
    if not notice.url or "enot.publicprocurement.be" in (notice.url or ""):
        url = _generate_ted_url(notice)
        if url:
            notice.url = url
            updated["url"] = True

    # Estimated value
    if not notice.estimated_value:
        # Cascade: lot (most specific) → proc → glo → framework (broadest)
        for key in ("estimated-value-lot", "estimated-value-proc", "estimated-value-glo",
                     "framework-estimated-value-glo", "estimated-value", "estimatedValue",
                     "value", "total-value"):
            v = raw.get(key)
            if v is not None:
                try:
                    notice.estimated_value = Decimal(str(v))
                    updated["estimated_value"] = True
                    break
                except Exception:
                    pass

    # Deadline
    if not notice.deadline:
        for key in ("deadline-receipt-tender-date-lot", "deadline-date-lot", "deadline-receipt-tender", "deadlineDate", "deadline",
                     "submission-deadline", "submissionDeadline"):
            v = raw.get(key)
            if v:
                try:
                    if isinstance(v, str):
                        # Try ISO format
                        if "T" in v:
                            notice.deadline = datetime.fromisoformat(v.replace("Z", "+00:00"))
                        else:
                            d = date.fromisoformat(v[:10])
                            notice.deadline = datetime(d.year, d.month, d.day)
                        updated["deadline"] = True
                        break
                except Exception:
                    pass

    # ── CAN (Contract Award Notice) fields from raw_data ─────────
    # Re-extract award fields using improved cascade (business-name, tender-value, winner-decision-date)

    # Award winner name
    if not notice.award_winner_name:
        winner = (
            _pick_text(raw.get("business-name"))
            or _pick_text(raw.get("winner-name"))
            or _pick_text(raw.get("organisation-name-tenderer"))
            or _pick_text(raw.get("organisation-partname-tenderer"))
        )
        if winner:
            notice.award_winner_name = _safe_str(winner, 500)
            updated["award_winner_name"] = True
        else:
            # Fallback: winner-country is better than nothing
            wc = _pick_text(raw.get("winner-country"))
            if wc and not notice.award_winner_name:
                notice.award_winner_name = _safe_str(wc, 500)
                updated["award_winner_name"] = True

    # Award value
    if not notice.award_value:
        for key in ("tender-value", "total-value", "tender-value-cur",
                     "result-value-lot", "contract-value-lot"):
            v = raw.get(key)
            if v is not None:
                try:
                    notice.award_value = Decimal(str(v))
                    updated["award_value"] = True
                    break
                except Exception:
                    pass

    # Award date
    if not notice.award_date:
        ad_raw = raw.get("winner-decision-date") or raw.get("award-date")
        if ad_raw:
            try:
                if isinstance(ad_raw, str):
                    notice.award_date = date.fromisoformat(ad_raw[:10])
                    updated["award_date"] = True
            except Exception:
                pass

    # Number of tenders received
    if not notice.number_tenders_received:
        nt = raw.get("received-submissions-type-val") or raw.get("number-of-tenders")
        if nt is not None:
            try:
                notice.number_tenders_received = int(nt)
                updated["number_tenders_received"] = True
            except (ValueError, TypeError):
                pass

    return updated


# ── BOSA enrichment from raw_data ────────────────────────────────────

def _enrich_bosa_notice(notice: Notice) -> dict[str, bool]:
    """Re-extract fields from BOSA raw_data. Returns dict of field: was_updated."""
    raw = notice.raw_data
    if not isinstance(raw, dict):
        return {}

    updated = {}

    # Organisation names from raw_data
    if not notice.organisation_names:
        org = raw.get("organisation")
        if isinstance(org, dict):
            org_names_raw = org.get("organisationNames")
            if isinstance(org_names_raw, list):
                names = {}
                for entry in org_names_raw:
                    if isinstance(entry, dict):
                        lang = entry.get("language", "").strip().upper()
                        text = entry.get("text", "").strip()
                        if lang and text:
                            names[lang[:3]] = text[:255]
                if names:
                    notice.organisation_names = names
                    updated["organisation_names"] = True
            elif isinstance(org_names_raw, dict):
                notice.organisation_names = {
                    k: str(v).strip()[:255]
                    for k, v in org_names_raw.items()
                    if v and str(v).strip()
                }
                if notice.organisation_names:
                    updated["organisation_names"] = True

        # Fallback: top-level organisationNames
        if not notice.organisation_names:
            top_names = raw.get("organisationNames")
            if isinstance(top_names, list):
                names = {}
                for entry in top_names:
                    if isinstance(entry, dict):
                        lang = str(entry.get("language", "")).strip().upper()
                        text = str(entry.get("text", "")).strip()
                        if lang and text:
                            names[lang[:3]] = text[:255]
                if names:
                    notice.organisation_names = names
                    updated["organisation_names"] = True

    # Description from raw_data
    if not notice.description:
        # Primary: dossier.descriptions (array of {language, text})
        dossier = raw.get("dossier")
        if isinstance(dossier, dict):
            descs = dossier.get("descriptions")
            if isinstance(descs, list) and descs:
                # Prefer FR, then NL, then first available
                desc_text = None
                for pref_lang in ("FR", "NL", "EN", "DE"):
                    for entry in descs:
                        if isinstance(entry, dict) and str(entry.get("language", "")).upper() == pref_lang:
                            t = str(entry.get("text", "")).strip()
                            if t:
                                desc_text = t
                                break
                    if desc_text:
                        break
                if not desc_text:
                    for entry in descs:
                        if isinstance(entry, dict):
                            t = str(entry.get("text", "")).strip()
                            if t:
                                desc_text = t
                                break
                if desc_text:
                    notice.description = desc_text[:10000]
                    updated["description"] = True

        # Fallback: top-level
        if not notice.description:
            desc = _pick_text(raw.get("description")) or _pick_text(raw.get("summary"))
            if desc:
                notice.description = desc[:10000]
                updated["description"] = True

    # ── Enrich short descriptions with lot info ───────────────────
    if notice.description and len(notice.description) < 200:
        lots_raw = raw.get("lots") or []
        if isinstance(lots_raw, list) and lots_raw:
            lot_texts = []
            for lot in lots_raw[:10]:  # max 10 lots to avoid bloat
                if not isinstance(lot, dict):
                    continue
                lot_descs = lot.get("descriptions") or lot.get("titles") or []
                if isinstance(lot_descs, list):
                    for entry in lot_descs:
                        if isinstance(entry, dict):
                            lang = str(entry.get("language", "")).upper()
                            text = str(entry.get("text", "")).strip()
                            if text and lang in ("FR", "NL", "EN", ""):
                                lot_num = lot.get("number", "?")
                                lot_texts.append(f"Lot {lot_num}: {text}")
                                break
            if lot_texts:
                enriched = notice.description + "\n\n" + "\n".join(lot_texts)
                notice.description = enriched[:10000]
                updated["description"] = True

    # Notice type: publicationType is the correct BOSA field
    if not notice.notice_type:
        nt = (
            raw.get("publicationType")
            or raw.get("noticeType")
            or raw.get("notice_type")
            or raw.get("type")
        )
        if nt:
            notice.notice_type = _safe_str(nt, 100)
            updated["notice_type"] = True

    # Form type: noticeSubType is the correct BOSA field
    if not notice.form_type:
        ft = (
            raw.get("noticeSubType")
            or raw.get("formType")
            or raw.get("form_type")
        )
        if ft:
            notice.form_type = _safe_str(ft, 100)
            updated["form_type"] = True

    # URL – also regenerate if old enot URL is present
    if not notice.url or "enot.publicprocurement.be" in (notice.url or ""):
        url = _generate_bosa_url(notice)
        if not url:
            url = raw.get("url")
        if url:
            notice.url = _safe_str(url, 1000)
            updated["url"] = True

    # NUTS codes
    if not notice.nuts_codes:
        nuts = raw.get("nutsCodes") or raw.get("nuts_codes") or raw.get("nutsCode")
        if isinstance(nuts, list) and nuts:
            codes = [str(n).strip() for n in nuts if n and str(n).strip()]
            if codes:
                notice.nuts_codes = codes
                updated["nuts_codes"] = True

    # ── Required accreditation from dossier.accreditations ────────
    if not notice.required_accreditation:
        dossier = raw.get("dossier")
        if isinstance(dossier, dict):
            accreditations = dossier.get("accreditations")
            if isinstance(accreditations, dict) and accreditations:
                parts = [f"{cat}{level}" for cat, level in sorted(accreditations.items())]
                notice.required_accreditation = ", ".join(parts)[:500]
                updated["required_accreditation"] = True
        # Fallback: pre-computed in raw_data by mapper
        if not notice.required_accreditation:
            ra = raw.get("required_accreditation")
            if ra and str(ra).strip():
                notice.required_accreditation = str(ra).strip()[:500]
                updated["required_accreditation"] = True

    # ── Keywords: enrich with natures + procedure type ────────────
    # Makes WORKS/SERVICES/SUPPLIES and OPEN/RESTRICTED searchable
    existing_kw = notice.keywords if isinstance(notice.keywords, list) else []
    existing_set = set(existing_kw)
    new_kw = list(existing_kw)
    kw_changed = False

    # Natures from raw_data
    natures = raw.get("natures") or []
    if isinstance(natures, list):
        for n in natures:
            tag = f"nature:{str(n).strip().upper()}"
            if tag not in existing_set and str(n).strip():
                new_kw.append(tag)
                existing_set.add(tag)
                kw_changed = True

    # Procedure type from dossier
    dossier = raw.get("dossier")
    if isinstance(dossier, dict):
        pt = dossier.get("procurementProcedureType")
        if pt:
            tag = f"procedure:{str(pt).strip()}"
            if tag not in existing_set:
                new_kw.append(tag)
                existing_set.add(tag)
                kw_changed = True
        spt = dossier.get("specialPurchasingTechnique")
        if spt:
            tag = f"technique:{str(spt).strip()}"
            if tag not in existing_set:
                new_kw.append(tag)
                existing_set.add(tag)
                kw_changed = True
        lb = dossier.get("legalBasis")
        if lb:
            tag = f"legal:{str(lb).strip()}"
            if tag not in existing_set:
                new_kw.append(tag)
                existing_set.add(tag)
                kw_changed = True

    # Also check pre-computed values in raw_data (from new mapper)
    for raw_key, prefix in (
        ("procurement_procedure_type", "procedure"),
        ("special_purchasing_technique", "technique"),
        ("legal_basis", "legal"),
    ):
        val = raw.get(raw_key)
        if val:
            tag = f"{prefix}:{str(val).strip()}"
            if tag not in existing_set:
                new_kw.append(tag)
                existing_set.add(tag)
                kw_changed = True

    if kw_changed:
        notice.keywords = new_kw
        updated["keywords"] = True

    return updated


# ── Backfill orchestrator ────────────────────────────────────────────

def backfill_from_raw_data(
    db: Session,
    source: Optional[str] = None,
    batch_size: int = 200,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """
    Re-extract missing fields from raw_data for all notices.
    No external API calls needed.

    Args:
        source: Optional filter (BOSA_EPROC, TED_EU)
        batch_size: Commit every N notices
        limit: Max notices to process (None = all)

    Returns:
        Summary with counts per field updated
    """
    query = db.query(Notice).filter(Notice.raw_data.isnot(None))

    if source:
        query = query.filter(Notice.source == source)

    total = query.count()
    notices = query.limit(limit) if limit else query
    notices = notices.all()

    stats = {
        "processed": 0,
        "enriched": 0,
        "fields_updated": {},
        "errors": 0,
    }

    for i, notice in enumerate(notices):
        try:
            if notice.source == NoticeSource.BOSA_EPROC.value:
                updated = _enrich_bosa_notice(notice)
            elif notice.source == NoticeSource.TED_EU.value:
                updated = _enrich_ted_notice(notice)
            else:
                updated = {}

            stats["processed"] += 1
            if updated:
                stats["enriched"] += 1
                for field in updated:
                    stats["fields_updated"][field] = stats["fields_updated"].get(field, 0) + 1

            if (i + 1) % batch_size == 0:
                db.commit()

        except Exception as e:
            stats["errors"] += 1
            logger.warning("Backfill error for notice %s: %s", notice.id, e)
            continue

    db.commit()

    stats["total_in_scope"] = len(notices)
    stats["total_in_db"] = total
    return stats


def refresh_search_vectors(db: Session) -> int:
    """
    Refresh tsvector search_vector column for all notices (PostgreSQL only).
    Uses the same trigger logic as migration 002.
    Returns number of rows updated.
    """
    if db.bind.dialect.name != "postgresql":
        logger.info("Skipping search_vector refresh (not PostgreSQL)")
        return 0

    result = db.execute(text("""
        UPDATE notices
        SET search_vector = to_tsvector('simple',
            coalesce(title, '') || ' ' || coalesce(description, '')
        )
    """))
    db.commit()
    return result.rowcount


# ── Data quality report ──────────────────────────────────────────────

def get_data_quality_report(db: Session) -> dict[str, Any]:
    """
    Generate data quality report: fill rate per field, per source.
    """
    total = db.query(func.count(Notice.id)).scalar() or 0
    if total == 0:
        return {"total": 0, "sources": {}, "fields": {}}

    # Per-source counts
    source_counts = dict(
        db.query(Notice.source, func.count(Notice.id))
        .group_by(Notice.source)
        .all()
    )

    # Fields to check — separate string fields (can check != '') from non-string (IS NOT NULL only)
    string_fields = [
        "title", "description", "notice_type",
        "cpv_main_code", "url", "form_type", "reference_number",
        "award_winner_name",
    ]
    non_string_fields = [
        "organisation_names", "nuts_codes",  # JSON
        "deadline", "estimated_value",       # datetime, numeric
        "award_value", "award_date",         # CAN fields
    ]

    # Global fill rates
    global_rates = {}
    for field in string_fields:
        col = getattr(Notice, field, None)
        if col is None:
            continue
        filled = db.query(func.count(Notice.id)).filter(
            col.isnot(None),
            col != "",
        ).scalar() or 0
        global_rates[field] = {
            "filled": filled,
            "total": total,
            "pct": round(100 * filled / total, 1),
        }
    for field in non_string_fields:
        col = getattr(Notice, field, None)
        if col is None:
            continue
        filled = db.query(func.count(Notice.id)).filter(
            col.isnot(None),
        ).scalar() or 0
        global_rates[field] = {
            "filled": filled,
            "total": total,
            "pct": round(100 * filled / total, 1),
        }

    # Per-source fill rates
    key_string = ["title", "description", "notice_type", "url"]
    key_non_string = ["organisation_names", "nuts_codes"]
    per_source = {}
    for source_val, source_total in source_counts.items():
        source_rates = {}
        for field in key_string:
            col = getattr(Notice, field, None)
            if col is None:
                continue
            filled = db.query(func.count(Notice.id)).filter(
                Notice.source == source_val,
                col.isnot(None),
                col != "",
            ).scalar() or 0
            source_rates[field] = {
                "filled": filled,
                "total": source_total,
                "pct": round(100 * filled / source_total, 1) if source_total else 0,
            }
        for field in key_non_string:
            col = getattr(Notice, field, None)
            if col is None:
                continue
            filled = db.query(func.count(Notice.id)).filter(
                Notice.source == source_val,
                col.isnot(None),
            ).scalar() or 0
            source_rates[field] = {
                "filled": filled,
                "total": source_total,
                "pct": round(100 * filled / source_total, 1) if source_total else 0,
            }
        per_source[source_val] = source_rates

    return {
        "total": total,
        "sources": source_counts,
        "fields": global_rates,
        "per_source": per_source,
    }


# ── CAN → CN merge (cleanup orphan result notices) ──────────────────

def merge_orphan_cans(db: Session, limit: int = 5000, dry_run: bool = False) -> dict[str, Any]:
    """
    Merge orphan CAN (form_type='result') records into their matching CN
    via procedure_id. Transfers award fields to CN and deletes the CAN.

    Args:
        db: Database session
        limit: Max records to process per call (avoids timeout)
        dry_run: If True, don't commit changes

    Returns:
        Stats dict with merged, orphaned (no matching CN), skipped, errors
    """
    TED_SOURCE = NoticeSource.TED_EU.value
    stats = {"merged": 0, "no_match": 0, "no_proc_id": 0, "deleted": 0, "errors": 0, "total_scanned": 0}

    # Find all CAN notices (form_type = 'result') from TED
    cans = (
        db.query(Notice)
        .filter(
            Notice.source == TED_SOURCE,
            Notice.form_type == "result",
        )
        .limit(limit)
        .all()
    )
    stats["total_scanned"] = len(cans)

    for can in cans:
        try:
            proc_id = can.procedure_id
            if not proc_id:
                # Try to extract from raw_data
                raw = can.raw_data or {}
                proc_id = (
                    raw.get("procedure-identifier")
                    or raw.get("procedureId")
                    or raw.get("procedure-id")
                )
                if proc_id:
                    proc_id = str(proc_id).strip()[:255]

            if not proc_id:
                stats["no_proc_id"] += 1
                continue

            # Find matching CN (non-result notice) with same procedure_id
            target_cn = (
                db.query(Notice)
                .filter(
                    Notice.source == TED_SOURCE,
                    Notice.procedure_id == proc_id,
                    Notice.form_type != "result",
                    Notice.id != can.id,
                )
                .first()
            )

            if not target_cn:
                stats["no_match"] += 1
                continue

            # Transfer award fields from CAN to CN (only if CN field is empty)
            changed = False
            if can.award_winner_name and not target_cn.award_winner_name:
                target_cn.award_winner_name = can.award_winner_name
                changed = True
            if can.award_value and not target_cn.award_value:
                target_cn.award_value = can.award_value
                changed = True
            if can.award_date and not target_cn.award_date:
                target_cn.award_date = can.award_date
                changed = True
            if can.number_tenders_received and not target_cn.number_tenders_received:
                target_cn.number_tenders_received = can.number_tenders_received
                changed = True
            if can.award_criteria_json and not target_cn.award_criteria_json:
                target_cn.award_criteria_json = can.award_criteria_json
                changed = True

            # Store CAN reference in CN's raw_data
            cn_raw = target_cn.raw_data or {}
            cn_raw["_can_source_id"] = can.source_id
            if can.publication_date:
                cn_raw["_can_publication_date"] = can.publication_date.isoformat()
            target_cn.raw_data = cn_raw

            # Ensure procedure_id is set on CN
            if not target_cn.procedure_id:
                target_cn.procedure_id = proc_id

            # Delete the orphan CAN record
            db.delete(can)
            stats["merged"] += 1
            stats["deleted"] += 1

        except Exception as e:
            logger.warning("merge_orphan_cans error for %s: %s", can.source_id, e)
            stats["errors"] += 1
            continue

    if not dry_run:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            stats["commit_error"] = str(e)
            logger.exception("merge_orphan_cans commit failed")

    return stats
