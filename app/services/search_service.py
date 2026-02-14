"""Notice search service — full-text (Postgres) with ILIKE fallback (SQLite).

Provides build_search_query() which returns a SQLAlchemy query + optional rank column,
and get_facets() for dynamic filter values.

Phase 12: Added deadline_after, value_min/max, active_only, multi-source filters,
          value_desc/asc sort, enriched facets (NUTS, deadline range, value range).
"""
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import case, cast, func, literal_column, or_, text, Float, String as sa_String
from sqlalchemy.orm import Session, Query

from app.models.notice import ProcurementNotice, NoticeSource
from app.services.dashboard_service import CPV_DIVISIONS as _CPV_DIVISIONS


# ── Helpers ──────────────────────────────────────────────────────────


def _is_postgres(db: Session) -> bool:
    """Check if connected to PostgreSQL (vs SQLite)."""
    return db.bind.dialect.name == "postgresql"


def _parse_tsquery(raw: str, expand_translations: bool = True) -> str:
    """
    Convert user input to a safe PostgreSQL tsquery string.
    When expand_translations is True, each term is expanded with FR/NL/EN
    translations using OR groups.

    'nettoyage bâtiment'  →  '(nettoyage:* | schoonmaak:* | cleaning:*) & (bâtiment:* | gebouw:* | building:*)'
    'route OR pont'       →  '(route:* | weg:* | road:*) | (pont:* | brug:* | bridge:*)'
    """
    raw = raw.strip()
    if not raw:
        return ""

    if expand_translations:
        from app.services.translation_service import expand_tsquery_terms
        expanded = expand_tsquery_terms(raw)
        if expanded:
            return expanded

    # Fallback: original logic without translation
    raw = re.sub(r"\bOR\b", "|", raw, flags=re.IGNORECASE)
    tokens = raw.split()
    result = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t in ("|", "&", "!"):
            result.append(t)
        else:
            clean = re.sub(r"[^\w\-*]", "", t, flags=re.UNICODE)
            if clean:
                result.append(f"{clean}:*")
    return " & ".join(result) if result else ""


def _source_value(source_str: str) -> Optional[str]:
    """Map user-friendly source name to DB enum value."""
    s = source_str.strip().upper()
    if s in ("BOSA", "BOSA_EPROC"):
        return NoticeSource.BOSA_EPROC.value
    elif s in ("TED", "TED_EU"):
        return NoticeSource.TED_EU.value
    return None


# ── Main search query builder ────────────────────────────────────────


def build_search_query(
    db: Session,
    q: Optional[str] = None,
    cpv: Optional[str] = None,
    nuts: Optional[str] = None,
    source: Optional[str] = None,
    sources: Optional[list[str]] = None,
    authority: Optional[str] = None,
    notice_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    deadline_before: Optional[date] = None,
    deadline_after: Optional[date] = None,
    value_min: Optional[float] = None,
    value_max: Optional[float] = None,
    active_only: bool = False,
    sort: str = "date_desc",
) -> tuple[Query, bool]:
    """
    Build a filtered + sorted query on ProcurementNotice.

    Returns (query, has_rank):
        - query: SQLAlchemy query ready for .count() / .offset().limit()
        - has_rank: True if relevance ranking is available (Postgres + keyword search)
    """
    is_pg = _is_postgres(db)
    has_rank = False

    query = db.query(ProcurementNotice)

    # ── Full-text / keyword search ──
    if q and q.strip():
        term = q.strip()
        if is_pg:
            tsq = _parse_tsquery(term)
            if tsq:
                query = query.filter(
                    text("search_vector @@ to_tsquery('simple', :tsq)").bindparams(tsq=tsq)
                )
                has_rank = True
            else:
                like = f"%{term}%"
                query = query.filter(
                    or_(
                        ProcurementNotice.title.ilike(like),
                        ProcurementNotice.description.ilike(like),
                    )
                )
        else:
            like = f"%{term}%"
            query = query.filter(
                or_(
                    ProcurementNotice.title.ilike(like),
                    ProcurementNotice.description.ilike(like),
                )
            )

    # ── CPV prefix filter ──
    if cpv and cpv.strip():
        cpv_clean = re.sub(r"[\-\s]", "", cpv.strip())
        query = query.filter(
            func.replace(func.coalesce(ProcurementNotice.cpv_main_code, ""), "-", "").like(f"{cpv_clean}%")
        )

    # ── NUTS prefix filter ──
    if nuts and nuts.strip():
        nuts_upper = nuts.strip().upper()
        if is_pg:
            query = query.filter(
                text(
                    "notices.nuts_codes IS NOT NULL "
                    "AND json_typeof(notices.nuts_codes) = 'array' "
                    "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes::jsonb) AS nc "
                    "WHERE nc LIKE :nuts_prefix)"
                ).bindparams(nuts_prefix=f"{nuts_upper}%")
            )
        else:
            query = query.filter(
                cast(ProcurementNotice.nuts_codes, sa_String()).like(f"%{nuts_upper}%")
            )

    # ── Source filter (single) ──
    if source and source.strip() and not sources:
        src_val = _source_value(source)
        if src_val:
            query = query.filter(ProcurementNotice.source == src_val)

    # ── Multi-source filter ──
    if sources and len(sources) > 0:
        src_vals = [v for s in sources if (v := _source_value(s))]
        if src_vals:
            query = query.filter(ProcurementNotice.source.in_(src_vals))

    # ── Authority / organisation name search ──
    if authority and authority.strip():
        auth_term = f"%{authority.strip()}%"
        if is_pg:
            query = query.filter(
                text(
                    "EXISTS (SELECT 1 FROM jsonb_each_text(notices.organisation_names::jsonb) AS kv "
                    "WHERE kv.value ILIKE :auth_term)"
                ).bindparams(auth_term=auth_term)
            )
        else:
            query = query.filter(
                cast(ProcurementNotice.organisation_names, sa_String()).ilike(auth_term)
            )

    # ── Notice type filter ──
    if notice_type and notice_type.strip():
        query = query.filter(ProcurementNotice.notice_type == notice_type.strip())

    # ── Date filters ──
    if date_from:
        query = query.filter(ProcurementNotice.publication_date >= date_from)
    if date_to:
        query = query.filter(ProcurementNotice.publication_date <= date_to)

    # ── Deadline filters ──
    if deadline_before:
        query = query.filter(ProcurementNotice.deadline <= deadline_before)
    if deadline_after:
        query = query.filter(ProcurementNotice.deadline >= deadline_after)

    # ── Active only (deadline in the future) ──
    if active_only:
        now = datetime.now(timezone.utc)
        query = query.filter(ProcurementNotice.deadline > now)

    # ── Estimated value range ──
    if value_min is not None:
        query = query.filter(ProcurementNotice.estimated_value >= value_min)
    if value_max is not None:
        query = query.filter(ProcurementNotice.estimated_value <= value_max)

    # ── Sorting ──
    if sort == "relevance" and has_rank and is_pg:
        tsq = _parse_tsquery(q.strip())
        query = query.order_by(
            text("ts_rank(search_vector, to_tsquery('simple', :tsq_rank)) DESC").bindparams(tsq_rank=tsq),
            ProcurementNotice.publication_date.desc().nulls_last(),
        )
    elif sort == "date_asc":
        query = query.order_by(ProcurementNotice.publication_date.asc().nulls_last())
    elif sort == "deadline":
        query = query.order_by(ProcurementNotice.deadline.asc().nulls_last())
    elif sort == "deadline_desc":
        query = query.order_by(ProcurementNotice.deadline.desc().nulls_last())
    elif sort == "value_desc":
        query = query.order_by(ProcurementNotice.estimated_value.desc().nulls_last())
    elif sort == "value_asc":
        query = query.order_by(ProcurementNotice.estimated_value.asc().nulls_last())
    elif sort == "award_desc":
        query = query.order_by(ProcurementNotice.award_value.desc().nulls_last())
    elif sort == "award_asc":
        query = query.order_by(ProcurementNotice.award_value.asc().nulls_last())
    elif sort == "award_date_desc":
        query = query.order_by(ProcurementNotice.award_date.desc().nulls_last())
    elif sort == "award_date_asc":
        query = query.order_by(ProcurementNotice.award_date.asc().nulls_last())
    elif sort == "cpv_asc":
        query = query.order_by(ProcurementNotice.cpv_main_code.asc().nulls_last())
    elif sort == "cpv_desc":
        query = query.order_by(ProcurementNotice.cpv_main_code.desc().nulls_last())
    elif sort == "source_asc":
        query = query.order_by(ProcurementNotice.source.asc())
    elif sort == "source_desc":
        query = query.order_by(ProcurementNotice.source.desc())
    else:
        # Default: date_desc
        query = query.order_by(ProcurementNotice.publication_date.desc().nulls_last())

    return query, has_rank


# ── Facets ───────────────────────────────────────────────────────────


def get_facets(db: Session) -> dict[str, Any]:
    """
    Return dynamic filter options for the UI:
    - sources: [{value, label, count}]
    - top_cpv: [{code, count}]  (top 20 CPV 2-digit divisions)
    - top_nuts: [{code, count}]  (top 20 NUTS country/region prefixes)
    - notice_types: [{value, count}]
    - date_range: {min, max}
    - deadline_range: {min, max}
    - value_range: {min, max}
    - active_count: int  (notices with deadline > now)
    """
    is_pg = _is_postgres(db)
    N = ProcurementNotice

    # Sources
    sources = (
        db.query(N.source, func.count(N.id))
        .group_by(N.source)
        .all()
    )
    source_list = [
        {"value": s, "label": "BOSA" if s == "BOSA_EPROC" else "TED", "count": c}
        for s, c in sources
    ]

    # Top CPV codes (2-digit divisions)
    if is_pg:
        cpv_rows = db.execute(text("""
            SELECT LEFT(REPLACE(cpv_main_code, '-', ''), 2) AS div, COUNT(*) AS cnt
            FROM notices
            WHERE cpv_main_code IS NOT NULL
            GROUP BY div
            ORDER BY cnt DESC
            LIMIT 20
        """)).all()
    else:
        cpv_rows = db.execute(text("""
            SELECT SUBSTR(REPLACE(cpv_main_code, '-', ''), 1, 2) AS div, COUNT(*) AS cnt
            FROM notices
            WHERE cpv_main_code IS NOT NULL
            GROUP BY div
            ORDER BY cnt DESC
            LIMIT 20
        """)).all()
    cpv_list = [{"code": row[0], "label": _CPV_DIVISIONS.get(row[0], ""), "count": row[1]} for row in cpv_rows if row[0]]

    # Top NUTS regions (2-char country codes from JSONB array)
    nuts_list = []
    if is_pg:
        try:
            nuts_rows = db.execute(text("""
                SELECT LEFT(nc, 2) AS country, COUNT(*) AS cnt
                FROM notices,
                     jsonb_array_elements_text(nuts_codes::jsonb) AS nc
                WHERE nuts_codes IS NOT NULL
                  AND jsonb_typeof(nuts_codes::jsonb) = 'array'
                GROUP BY country
                ORDER BY cnt DESC
                LIMIT 20
            """)).all()
            nuts_list = [{"code": row[0], "count": row[1]} for row in nuts_rows if row[0]]
        except Exception:
            pass  # Graceful degradation if NUTS data is sparse

    # Notice types
    type_rows = (
        db.query(N.notice_type, func.count(N.id))
        .filter(N.notice_type.isnot(None))
        .group_by(N.notice_type)
        .order_by(func.count(N.id).desc())
        .limit(20)
        .all()
    )
    type_list = [{"value": t, "count": c} for t, c in type_rows]

    # Date range (publication)
    date_range = db.query(
        func.min(N.publication_date),
        func.max(N.publication_date),
    ).first()
    date_info = {
        "min": date_range[0].isoformat() if date_range and date_range[0] else None,
        "max": date_range[1].isoformat() if date_range and date_range[1] else None,
    }

    # Deadline range
    deadline_range = db.query(
        func.min(N.deadline),
        func.max(N.deadline),
    ).first()
    deadline_info = {
        "min": deadline_range[0].isoformat() if deadline_range and deadline_range[0] else None,
        "max": deadline_range[1].isoformat() if deadline_range and deadline_range[1] else None,
    }

    # Value range
    value_range = db.query(
        func.min(N.estimated_value),
        func.max(N.estimated_value),
    ).filter(N.estimated_value.isnot(None), N.estimated_value > 0).first()
    value_info = {
        "min": float(value_range[0]) if value_range and value_range[0] else None,
        "max": float(value_range[1]) if value_range and value_range[1] else None,
    }

    # Active count (deadline > now)
    now = datetime.now(timezone.utc)
    active_count = (
        db.query(func.count(N.id))
        .filter(N.deadline > now)
        .scalar()
    ) or 0

    # Total
    total = db.query(func.count(N.id)).scalar() or 0

    return {
        "total_notices": total,
        "active_count": active_count,
        "sources": source_list,
        "top_cpv_divisions": cpv_list,
        "top_nuts_countries": nuts_list,
        "notice_types": type_list,
        "date_range": date_info,
        "deadline_range": deadline_info,
        "value_range": value_info,
    }
