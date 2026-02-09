"""Dashboard KPI queries — all reads, no writes."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, text, case, literal_column
from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice as Notice

logger = logging.getLogger(__name__)


# ── Overview KPIs ────────────────────────────────────────────────────


def get_overview(db: Session) -> dict[str, Any]:
    """
    Main dashboard KPIs:
    - total notices, active (deadline > now), by source
    - value stats (min/max/avg of estimated_value)
    - publication freshness (newest, oldest, median age)
    """
    now = datetime.now(timezone.utc)

    total = db.query(func.count(Notice.id)).scalar() or 0

    active = db.query(func.count(Notice.id)).filter(
        Notice.deadline > now
    ).scalar() or 0

    # By source
    source_rows = db.query(
        Notice.source, func.count(Notice.id)
    ).group_by(Notice.source).all()
    by_source = {str(src): cnt for src, cnt in source_rows}

    # Value stats (only where estimated_value is set)
    val_stats = db.query(
        func.count(Notice.estimated_value),
        func.min(Notice.estimated_value),
        func.max(Notice.estimated_value),
        func.avg(Notice.estimated_value),
    ).filter(Notice.estimated_value.isnot(None)).first()

    value_count, value_min, value_max, value_avg = val_stats or (0, None, None, None)

    # Publication freshness
    newest = db.query(func.max(Notice.publication_date)).scalar()
    oldest = db.query(func.min(Notice.publication_date)).scalar()

    # Notices added in last 24h / 7d
    added_24h = db.query(func.count(Notice.id)).filter(
        Notice.created_at >= now - timedelta(hours=24)
    ).scalar() or 0

    added_7d = db.query(func.count(Notice.id)).filter(
        Notice.created_at >= now - timedelta(days=7)
    ).scalar() or 0

    # Deadlines expiring soon (next 7 days)
    expiring_7d = db.query(func.count(Notice.id)).filter(
        Notice.deadline > now,
        Notice.deadline <= now + timedelta(days=7),
    ).scalar() or 0

    return {
        "total_notices": total,
        "active_notices": active,
        "expiring_7d": expiring_7d,
        "by_source": by_source,
        "added_24h": added_24h,
        "added_7d": added_7d,
        "newest_publication": str(newest) if newest else None,
        "oldest_publication": str(oldest) if oldest else None,
        "value_stats": {
            "notices_with_value": value_count or 0,
            "min_eur": float(value_min) if value_min else None,
            "max_eur": float(value_max) if value_max else None,
            "avg_eur": round(float(value_avg), 2) if value_avg else None,
        },
    }


# ── Publication trends ───────────────────────────────────────────────


def get_trends(db: Session, days: int = 30, group_by: str = "day") -> dict[str, Any]:
    """
    Daily or weekly publication counts for charting.
    Returns [{date, count, source}, ...] for the last N days.
    """
    cutoff = date.today() - timedelta(days=days)

    if group_by == "week":
        # Group by ISO week
        rows = db.execute(text("""
            SELECT
                source,
                CAST(EXTRACT(ISOYEAR FROM publication_date) AS INTEGER) AS yr,
                CAST(EXTRACT(WEEK FROM publication_date) AS INTEGER) AS wk,
                COUNT(*) AS cnt
            FROM notices
            WHERE publication_date >= :cutoff
            GROUP BY source, yr, wk
            ORDER BY yr, wk
        """), {"cutoff": cutoff}).fetchall()

        points = [
            {"source": r[0], "year": r[1], "week": r[2], "count": r[3]}
            for r in rows
        ]
    else:
        rows = db.execute(text("""
            SELECT
                source,
                CAST(publication_date AS VARCHAR) AS pub_date,
                COUNT(*) AS cnt
            FROM notices
            WHERE publication_date >= :cutoff
            GROUP BY source, publication_date
            ORDER BY publication_date
        """), {"cutoff": cutoff}).fetchall()

        points = [
            {"source": r[0], "date": r[1], "count": r[2]}
            for r in rows
        ]

    # Also totals per source
    totals = db.execute(text("""
        SELECT source, COUNT(*) FROM notices
        WHERE publication_date >= :cutoff
        GROUP BY source
    """), {"cutoff": cutoff}).fetchall()

    return {
        "period_days": days,
        "group_by": group_by,
        "cutoff": str(cutoff),
        "totals_by_source": {str(r[0]): r[1] for r in totals},
        "data": points,
    }


# ── Top CPV codes ────────────────────────────────────────────────────

# Common CPV division names (2-digit codes)
CPV_DIVISIONS = {
    "03": "Agriculture & forestry",
    "09": "Petroleum & fuel",
    "14": "Mining & quarrying",
    "15": "Food & beverages",
    "18": "Clothing & textiles",
    "22": "Printed matter",
    "24": "Chemical products",
    "30": "Office & computing",
    "31": "Electrical machinery",
    "32": "Radio & telecom",
    "33": "Medical equipment",
    "34": "Transport equipment",
    "35": "Security & defence",
    "37": "Musical instruments & sport",
    "38": "Laboratory equipment",
    "39": "Furniture & furnishings",
    "42": "Industrial machinery",
    "43": "Mining machinery",
    "44": "Construction materials",
    "45": "Construction work",
    "48": "Software packages",
    "50": "Repair & maintenance",
    "51": "Installation services",
    "55": "Hotel & restaurant",
    "60": "Transport services",
    "63": "Transport support",
    "64": "Postal & telecom services",
    "65": "Public utilities",
    "66": "Financial & insurance",
    "70": "Real estate services",
    "71": "Architecture & engineering",
    "72": "IT services",
    "73": "R&D services",
    "75": "Public administration",
    "76": "Oil & gas services",
    "77": "Agriculture & forestry services",
    "79": "Business services",
    "80": "Education & training",
    "85": "Health & social services",
    "90": "Sewage & refuse",
    "92": "Recreation & culture",
    "98": "Other community services",
}


def get_top_cpv(db: Session, limit: int = 20, active_only: bool = False) -> dict[str, Any]:
    """Top CPV divisions by notice count."""
    now = datetime.now(timezone.utc)

    query = db.query(
        func.substr(Notice.cpv_main_code, 1, 2).label("division"),
        func.count(Notice.id).label("cnt"),
    ).filter(
        Notice.cpv_main_code.isnot(None),
        func.length(Notice.cpv_main_code) >= 2,
    )

    if active_only:
        query = query.filter(Notice.deadline > now)

    rows = query.group_by("division").order_by(text("cnt DESC")).limit(limit).all()

    return {
        "active_only": active_only,
        "data": [
            {
                "code": r.division,
                "label": CPV_DIVISIONS.get(r.division, "Other"),
                "count": r.cnt,
            }
            for r in rows
        ],
    }


# ── Top authorities ──────────────────────────────────────────────────


def get_top_authorities(db: Session, limit: int = 20, active_only: bool = False) -> dict[str, Any]:
    """
    Top contracting authorities by notice count.
    Uses organisation_names JSON field (multilingual dict).
    Falls back to organisation_id if names are missing.
    """
    now = datetime.now(timezone.utc)

    # For PostgreSQL: extract first value from organisation_names JSON
    # organisation_names is like {"fr": "Ville de Bruxelles", "nl": "Stad Brussel"}
    # We'll use raw SQL for JSON extraction
    try:
        query_str = """
            SELECT
                COALESCE(
                    (SELECT value FROM jsonb_each_text(organisation_names::jsonb) LIMIT 1),
                    organisation_id,
                    'Unknown'
                ) AS authority_name,
                COUNT(*) AS cnt
            FROM notices
            WHERE organisation_names IS NOT NULL
              AND jsonb_typeof(organisation_names::jsonb) = 'object'
        """
        if active_only:
            query_str += " AND deadline > :now"

        query_str += """
            GROUP BY authority_name
            ORDER BY cnt DESC
            LIMIT :limit
        """

        params: dict[str, Any] = {"limit": limit}
        if active_only:
            params["now"] = now.isoformat()

        rows = db.execute(text(query_str), params).fetchall()

        return {
            "active_only": active_only,
            "data": [
                {"name": r[0], "count": r[1]}
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning("Top authorities query failed (JSON compat): %s", e)
        # Fallback: group by organisation_id
        query = db.query(
            Notice.organisation_id,
            func.count(Notice.id).label("cnt"),
        ).filter(Notice.organisation_id.isnot(None))

        if active_only:
            query = query.filter(Notice.deadline > now)

        rows = query.group_by(Notice.organisation_id).order_by(
            text("cnt DESC")
        ).limit(limit).all()

        return {
            "active_only": active_only,
            "data": [
                {"name": r[0] or "Unknown", "count": r[1]}
                for r in rows
            ],
        }


# ── Import health ────────────────────────────────────────────────────


def get_import_health(db: Session) -> dict[str, Any]:
    """
    Import pipeline health:
    - Last import run per source (time, counts, errors)
    - Data freshness (gap between newest notice and now)
    - Field fill rates (how complete is the data)
    """
    # Last import runs
    try:
        runs = db.execute(text("""
            SELECT source,
                   MAX(started_at) AS last_run,
                   SUM(created_count) AS total_created,
                   SUM(updated_count) AS total_updated,
                   SUM(error_count) AS total_errors,
                   COUNT(*) AS run_count
            FROM import_runs
            GROUP BY source
        """)).mappings().all()
        import_summary = {
            r["source"]: {
                "last_run": str(r["last_run"]) if r["last_run"] else None,
                "total_created": r["total_created"] or 0,
                "total_updated": r["total_updated"] or 0,
                "total_errors": r["total_errors"] or 0,
                "run_count": r["run_count"] or 0,
            }
            for r in runs
        }
    except Exception:
        import_summary = {"error": "import_runs table not available"}

    # Data freshness
    newest_pub = db.query(func.max(Notice.publication_date)).scalar()
    newest_created = db.query(func.max(Notice.created_at)).scalar()

    now = datetime.now(timezone.utc)
    freshness_hours = None
    if newest_created:
        if newest_created.tzinfo is None:
            from datetime import timezone as tz
            newest_created = newest_created.replace(tzinfo=tz.utc)
        freshness_hours = round((now - newest_created).total_seconds() / 3600, 1)

    # Field fill rates (sample-based for performance)
    total = db.query(func.count(Notice.id)).scalar() or 1  # avoid div/0

    fill_fields = {
        "title": Notice.title,
        "description": Notice.description,
        "cpv_main_code": Notice.cpv_main_code,
        "deadline": Notice.deadline,
        "estimated_value": Notice.estimated_value,
        "url": Notice.url,
        "organisation_names": Notice.organisation_names,
        "nuts_codes": Notice.nuts_codes,
        "notice_type": Notice.notice_type,
    }

    fill_rates = {}
    for field_name, column in fill_fields.items():
        filled = db.query(func.count(Notice.id)).filter(
            column.isnot(None)
        ).scalar() or 0
        fill_rates[field_name] = round(filled / total * 100, 1)

    return {
        "imports": import_summary,
        "freshness": {
            "newest_publication_date": str(newest_pub) if newest_pub else None,
            "newest_record_created": str(newest_created) if newest_created else None,
            "hours_since_last_import": freshness_hours,
        },
        "field_fill_rates_pct": fill_rates,
    }
