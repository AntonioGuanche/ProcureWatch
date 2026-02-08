"""Notice search service — full-text (Postgres) with ILIKE fallback (SQLite).

Provides build_search_query() which returns a SQLAlchemy query + optional rank column,
and get_facets() for dynamic filter values.
"""
import re
from datetime import date
from typing import Any, Optional

from sqlalchemy import case, cast, func, literal_column, or_, text, Float, String as sa_String
from sqlalchemy.orm import Session, Query

from app.models.notice import ProcurementNotice, NoticeSource


# ── Helpers ──────────────────────────────────────────────────────────


def _is_postgres(db: Session) -> bool:
    """Check if connected to PostgreSQL (vs SQLite)."""
    return db.bind.dialect.name == "postgresql"


def _parse_tsquery(raw: str) -> str:
    """
    Convert user input to a safe PostgreSQL tsquery string.
    'construction bâtiment'  →  'construction & bâtiment'
    'route OR pont'          →  'route | pont'
    '"travaux publics"'      →  kept as phrase (tsquery handles it)
    """
    raw = raw.strip()
    if not raw:
        return ""
    # Replace OR (case-insensitive) with |
    raw = re.sub(r"\bOR\b", "|", raw, flags=re.IGNORECASE)
    # Split on whitespace, rejoin with & (AND) unless already an operator
    tokens = raw.split()
    result = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t in ("|", "&", "!"):
            result.append(t)
        else:
            # Remove characters that break tsquery
            clean = re.sub(r"[^\w\-*]", "", t, flags=re.UNICODE)
            if clean:
                # Add prefix matching with :*
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
    authority: Optional[str] = None,
    notice_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    deadline_before: Optional[date] = None,
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
                # Fallback if tsquery parse produced nothing
                like = f"%{term}%"
                query = query.filter(
                    or_(
                        ProcurementNotice.title.ilike(like),
                        ProcurementNotice.description.ilike(like),
                    )
                )
        else:
            # SQLite fallback
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
            # JSONB array contains check: any element starts with prefix
            query = query.filter(
                text(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text(notices.nuts_codes) AS nc "
                    "WHERE nc LIKE :nuts_prefix)"
                ).bindparams(nuts_prefix=f"{nuts_upper}%")
            )
        else:
            # SQLite: basic JSON text search
            query = query.filter(
                cast(ProcurementNotice.nuts_codes, sa_String()).like(f"%{nuts_upper}%")
            )

    # ── Source filter ──
    if source and source.strip():
        src_val = _source_value(source)
        if src_val:
            query = query.filter(ProcurementNotice.source == src_val)

    # ── Authority / organisation name search ──
    if authority and authority.strip():
        auth_term = f"%{authority.strip()}%"
        if is_pg:
            # Search in JSONB values
            query = query.filter(
                text(
                    "EXISTS (SELECT 1 FROM jsonb_each_text(notices.organisation_names) AS kv "
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

    # ── Deadline filter ──
    if deadline_before:
        query = query.filter(ProcurementNotice.deadline <= deadline_before)

    # ── Sorting ──
    if sort == "relevance" and has_rank and is_pg:
        tsq = _parse_tsquery(q.strip())
        query = query.order_by(
            text("ts_rank(search_vector, to_tsquery('simple', :tsq)) DESC").bindparams(tsq=tsq),
            ProcurementNotice.publication_date.desc().nulls_last(),
        )
    elif sort == "date_asc":
        query = query.order_by(ProcurementNotice.publication_date.asc().nulls_last())
    elif sort == "deadline":
        query = query.order_by(ProcurementNotice.deadline.asc().nulls_last())
    else:
        # Default: date_desc
        query = query.order_by(ProcurementNotice.publication_date.desc().nulls_last())

    return query, has_rank


# ── Facets ───────────────────────────────────────────────────────────


def get_facets(db: Session) -> dict[str, Any]:
    """
    Return dynamic filter options for the UI:
    - sources: [{value, label, count}]
    - top_cpv: [{code, count}]  (top 20 CPV prefixes)
    - notice_types: [{value, count}]
    - date_range: {min, max}
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
    cpv_list = [{"code": row[0], "count": row[1]} for row in cpv_rows if row[0]]

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

    # Date range
    date_range = db.query(
        func.min(N.publication_date),
        func.max(N.publication_date),
    ).first()
    date_info = {
        "min": date_range[0].isoformat() if date_range and date_range[0] else None,
        "max": date_range[1].isoformat() if date_range and date_range[1] else None,
    }

    # Total
    total = db.query(func.count(N.id)).scalar() or 0

    return {
        "total_notices": total,
        "sources": source_list,
        "top_cpv_divisions": cpv_list,
        "notice_types": type_list,
        "date_range": date_info,
    }

