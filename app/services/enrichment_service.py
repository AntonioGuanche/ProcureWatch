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
    """Generate TED notice URL from publication number or source_id.
    Format: https://ted.europa.eu/en/notice/-/detail/{publication-number}
    """
    pub_num = notice.source_id
    if not pub_num:
        return None
    # Clean: remove spaces, ensure format
    pub_num = pub_num.strip()
    if pub_num:
        return f"https://ted.europa.eu/en/notice/-/detail/{pub_num}"
    return None


def _generate_bosa_url(notice: Notice) -> Optional[str]:
    """Generate BOSA notice URL from workspace ID.
    Format: https://enot.publicprocurement.be/changeNotice/view/{workspace_id}
    """
    ws_id = notice.publication_workspace_id or notice.source_id
    if not ws_id:
        return None
    return f"https://enot.publicprocurement.be/changeNotice/view/{ws_id.strip()}"


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
            or _pick_text(raw.get("description"))
            or _pick_text(raw.get("summary"))
            or _pick_text(raw.get("short-description"))
        )
        if desc:
            notice.description = desc[:10000]
            updated["description"] = True

    # Notice type
    if not notice.notice_type:
        nt = (
            raw.get("notice-type")
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
            raw.get("place-of-performance")
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
    if not notice.url:
        url = _generate_ted_url(notice)
        if url:
            notice.url = url
            updated["url"] = True

    # Estimated value
    if not notice.estimated_value:
        for key in ("estimated-value", "estimatedValue", "value", "total-value"):
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
        for key in ("deadline-receipt-tender", "deadlineDate", "deadline",
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
        desc = _pick_text(raw.get("description")) or _pick_text(raw.get("summary"))
        if not desc:
            # Try dossier.titles as fallback description
            dossier = raw.get("dossier")
            if isinstance(dossier, dict):
                desc = _pick_text(dossier.get("description")) or _pick_text(dossier.get("summary"))
        if desc:
            notice.description = desc[:10000]
            updated["description"] = True

    # Notice type
    if not notice.notice_type:
        nt = raw.get("noticeType") or raw.get("notice_type") or raw.get("type")
        if nt:
            notice.notice_type = _safe_str(nt, 100)
            updated["notice_type"] = True

    # URL
    if not notice.url:
        url = raw.get("url")
        if not url:
            url = _generate_bosa_url(notice)
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

    # Fields to check
    fields = [
        "title", "description", "organisation_names", "notice_type",
        "cpv_main_code", "nuts_codes", "url", "deadline",
        "estimated_value", "form_type", "reference_number",
    ]

    # Global fill rates
    global_rates = {}
    for field in fields:
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

    # Per-source fill rates for key fields
    key_fields = ["title", "description", "organisation_names", "notice_type", "url", "nuts_codes"]
    per_source = {}
    for source_val, source_total in source_counts.items():
        source_rates = {}
        for field in key_fields:
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
        per_source[source_val] = source_rates

    return {
        "total": total,
        "sources": source_counts,
        "fields": global_rates,
        "per_source": per_source,
    }
