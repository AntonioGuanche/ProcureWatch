"""CPV Intelligence Service — sector-level market analytics.

Provides deep analytics for user-selected CPV groups (3-digit codes):
  1. Volume & Valeur (yearly/monthly trends)
  2. Top entreprises (award winners by count & value)
  3. Top pouvoirs adjudicateurs (contracting authorities)
  4. Niveau de concurrence (tender count distribution)
  5. Types de procédures (open/restricted/negotiated)
  6. Répartition géographique (NUTS regions)
  7. Saisonnalité (monthly publication patterns)
  8. Distribution des montants (value buckets)
  9. Marchés sans concurrence (single-bid contracts)
  10. Délai moyen d'attribution (publication → award)
  11. Opportunités en cours (active notices with deadline)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cpv_reference import CPV_REFERENCE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CPV group label lookup (3-digit code → French label)
# Built from the CPV_REFERENCE list: pick the broadest label per 3-digit group.
# ---------------------------------------------------------------------------
_CPV_GROUP_LABELS: dict[str, str] = {}
for _code, _label in CPV_REFERENCE:
    _group = _code[:3]
    # Keep the first (broadest) label per group
    if _group not in _CPV_GROUP_LABELS:
        _CPV_GROUP_LABELS[_group] = _label

# Division-level labels (2 digits) for fallback when 3-digit group is unknown
_CPV_DIVISION_LABELS: dict[str, str] = {
    "03": "Agriculture & sylviculture",
    "09": "Pétrole, combustibles & électricité",
    "14": "Exploitation minière",
    "15": "Produits alimentaires & boissons",
    "16": "Machines agricoles",
    "18": "Vêtements & textiles",
    "19": "Cuir & textiles",
    "22": "Imprimés & produits connexes",
    "24": "Produits chimiques",
    "30": "Machines de bureau & matériel informatique",
    "31": "Machines & appareils électriques",
    "32": "Équipements radio, TV & communication",
    "33": "Matériel médical & pharmaceutique",
    "34": "Équipements de transport",
    "35": "Équipements de sécurité & défense",
    "37": "Instruments de musique & sport",
    "38": "Équipements de laboratoire & optiques",
    "39": "Meubles & aménagements",
    "41": "Eaux collectées & épurées",
    "42": "Machines industrielles",
    "43": "Machines pour l'exploitation minière",
    "44": "Matériaux de construction",
    "45": "Travaux de construction",
    "48": "Logiciels & systèmes d'information",
    "50": "Réparation & entretien",
    "51": "Services d'installation",
    "55": "Hôtellerie & restauration",
    "60": "Services de transport",
    "63": "Services auxiliaires de transport",
    "64": "Services postaux & télécommunications",
    "65": "Services publics (eau, énergie)",
    "66": "Services financiers & assurance",
    "70": "Services immobiliers",
    "71": "Architecture & ingénierie",
    "72": "Services informatiques",
    "73": "Recherche & développement",
    "75": "Administration publique & défense",
    "76": "Services liés au pétrole & gaz",
    "77": "Services agricoles & horticoles",
    "79": "Services aux entreprises",
    "80": "Enseignement & formation",
    "85": "Santé & services sociaux",
    "90": "Assainissement & environnement",
    "92": "Loisirs, culture & sport",
    "98": "Autres services communautaires",
}


def cpv_group_label(group_code: str) -> str:
    """Return French label for a 3-digit CPV group code."""
    if group_code in _CPV_GROUP_LABELS:
        return _CPV_GROUP_LABELS[group_code]
    # Fallback: use division label
    div = group_code[:2]
    if div in _CPV_DIVISION_LABELS:
        return f"{_CPV_DIVISION_LABELS[div]} ({group_code})"
    return f"CPV {group_code}xx"


def list_cpv_groups() -> list[dict[str, str]]:
    """Return all known CPV groups with labels for the selector UI (static)."""
    return [
        {"code": code, "label": label}
        for code, label in sorted(_CPV_GROUP_LABELS.items())
    ]


def list_cpv_groups_from_db(db: Session) -> list[dict[str, Any]]:
    """Query the DB for ALL distinct 3-digit CPV group prefixes with counts.

    This ensures every CPV code present in the data is selectable,
    not just the ones in the static reference list.
    """
    rows = db.execute(text("""
        SELECT
            SUBSTRING(cpv_main_code FROM 1 FOR 3) AS grp,
            COUNT(*) AS cnt
        FROM notices
        WHERE cpv_main_code IS NOT NULL
          AND LENGTH(cpv_main_code) >= 3
        GROUP BY grp
        ORDER BY cnt DESC
    """)).mappings().all()

    return [
        {
            "code": r["grp"],
            "label": cpv_group_label(r["grp"]),
            "count": r["cnt"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _cpv_filter_clause(cpv_groups: list[str]) -> str:
    """Build SQL WHERE clause for CPV group filtering.

    Uses SUBSTRING to match 3-digit group prefix.
    Multiple groups are OR'd together.
    """
    if len(cpv_groups) == 1:
        return "SUBSTRING(cpv_main_code FROM 1 FOR 3) = :cpv0"
    clauses = [f"SUBSTRING(cpv_main_code FROM 1 FOR 3) = :cpv{i}"
               for i in range(len(cpv_groups))]
    return "(" + " OR ".join(clauses) + ")"


def _cpv_params(cpv_groups: list[str]) -> dict[str, str]:
    """Build SQL params dict for CPV group codes."""
    return {f"cpv{i}": g for i, g in enumerate(cpv_groups)}


# ---------------------------------------------------------------------------
# 1. Volume & Valeur
# ---------------------------------------------------------------------------

def get_volume_value(
    db: Session, cpv_groups: list[str], months: int = 24,
) -> dict[str, Any]:
    """Yearly and monthly publication counts + value aggregates."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "cutoff": cutoff}

    # Monthly breakdown
    monthly = db.execute(text(f"""
        SELECT
            TO_CHAR(publication_date, 'YYYY-MM') AS month,
            COUNT(*) AS notice_count,
            COUNT(CASE WHEN award_winner_name IS NOT NULL AND award_winner_name != '—' THEN 1 END) AS awarded_count,
            COALESCE(SUM(estimated_value), 0) AS total_estimated,
            COALESCE(SUM(award_value), 0) AS total_awarded,
            COALESCE(AVG(estimated_value) FILTER (WHERE estimated_value IS NOT NULL), 0) AS avg_estimated,
            COALESCE(AVG(award_value) FILTER (WHERE award_value IS NOT NULL), 0) AS avg_awarded
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND publication_date >= :cutoff
        GROUP BY month
        ORDER BY month
    """), params).mappings().all()

    # Yearly breakdown
    yearly = db.execute(text(f"""
        SELECT
            EXTRACT(YEAR FROM publication_date)::INTEGER AS year,
            COUNT(*) AS notice_count,
            COUNT(CASE WHEN award_winner_name IS NOT NULL AND award_winner_name != '—' THEN 1 END) AS awarded_count,
            COALESCE(SUM(estimated_value), 0) AS total_estimated,
            COALESCE(SUM(award_value), 0) AS total_awarded
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND publication_date IS NOT NULL
        GROUP BY year
        ORDER BY year
    """), _cpv_params(cpv_groups)).mappings().all()

    # Totals
    totals = db.execute(text(f"""
        SELECT
            COUNT(*) AS total_notices,
            COUNT(CASE WHEN award_winner_name IS NOT NULL AND award_winner_name != '—' THEN 1 END) AS total_awarded,
            COALESCE(SUM(estimated_value), 0) AS sum_estimated,
            COALESCE(SUM(award_value), 0) AS sum_awarded,
            COALESCE(AVG(estimated_value) FILTER (WHERE estimated_value IS NOT NULL), 0) AS avg_estimated,
            COALESCE(AVG(award_value) FILTER (WHERE award_value IS NOT NULL), 0) AS avg_awarded
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
    """), _cpv_params(cpv_groups)).mappings().first()

    return {
        "totals": {
            "total_notices": totals["total_notices"],
            "total_awarded": totals["total_awarded"],
            "sum_estimated_eur": float(totals["sum_estimated"]),
            "sum_awarded_eur": float(totals["sum_awarded"]),
            "avg_estimated_eur": round(float(totals["avg_estimated"]), 2),
            "avg_awarded_eur": round(float(totals["avg_awarded"]), 2),
        },
        "monthly": [
            {
                "month": r["month"],
                "count": r["notice_count"],
                "awarded": r["awarded_count"],
                "total_estimated": float(r["total_estimated"]),
                "total_awarded": float(r["total_awarded"]),
                "avg_estimated": round(float(r["avg_estimated"]), 2),
                "avg_awarded": round(float(r["avg_awarded"]), 2),
            }
            for r in monthly
        ],
        "yearly": [
            {
                "year": r["year"],
                "count": r["notice_count"],
                "awarded": r["awarded_count"],
                "total_estimated": float(r["total_estimated"]),
                "total_awarded": float(r["total_awarded"]),
            }
            for r in yearly
        ],
    }


# ---------------------------------------------------------------------------
# 2. Top entreprises (award winners) — with name normalization
# ---------------------------------------------------------------------------

# SQL expression to normalize company names across ALL EU jurisdictions.
# Two-pass approach:
#   Pass 1: strip dotted abbreviations (N.V., B.V., S.A., etc.)
#   Pass 2: strip plain word suffixes using \\y (PostgreSQL word boundary)
#   Note: \\b is POSIX backspace in PostgreSQL — use \\y instead.

_SUFFIXES_DOTTED = (
    "N\\.V\\.|B\\.V\\.|S\\.A\\.|S\\.R\\.L\\.|S\\.P\\.R\\.L\\."
    "|B\\.V\\.B\\.A\\.|V\\.Z\\.W\\.|A\\.S\\.B\\.L\\.|C\\.V\\.B\\.A\\."
    "|G\\.M\\.B\\.H\\.|S\\.A\\.R\\.L\\.|S\\.P\\.A\\.|S\\.C\\.R\\.L\\."
)

_SUFFIXES_PLAIN = (
    "NV|SA|BV|BVBA|SRL|SPRL|VZW|ASBL|CVBA|CV|SC|SCRL"
    "|AG|GMBH|KG|OHG|EG|UG|MBH|EWIV"
    "|SAS|SARL|SCI|SNC|EURL|SCM|GIE"
    "|SPA|SCARL"
    "|SL|SLU|SAU|LDA"
    "|LTD|PLC|LLP|INC|CIC|CORP|CO"
    "|ZOO|SP|SRO|AS|APS|AB|OY|OYJ"
    "|SE|EEIG|GEIE|VOF"
)

_NORM_SQL = f"""
TRIM(BOTH ' ' FROM
  REGEXP_REPLACE(
    REGEXP_REPLACE(
      REGEXP_REPLACE(
        REGEXP_REPLACE(
          UPPER(TRIM(award_winner_name)),
          '\\s*({_SUFFIXES_DOTTED})\\s*$', '', 'i'
        ),
        '\\s+({_SUFFIXES_PLAIN})\\y\\.?\\s*$', '', 'i'
      ),
      '[.,:;\\-/\\s]+$', ''
    ),
    '\\s+', ' ', 'g'
  )
)
"""


def get_top_winners(
    db: Session, cpv_groups: list[str], limit: int = 20,
) -> list[dict[str, Any]]:
    """Top companies by contracts won, with fuzzy name grouping.

    Company names like "Krinkels NV", "Krinkels nv", "Krinkels"
    are grouped together. The most frequently used original name
    is displayed via MODE().
    """
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "limit": limit}

    rows = db.execute(text(f"""
        WITH norm AS (
            SELECT
                award_winner_name,
                {_NORM_SQL} AS norm_name,
                award_value,
                award_date
            FROM notices
            WHERE {cpv_clause}
              AND cpv_main_code IS NOT NULL
              AND award_winner_name IS NOT NULL AND award_winner_name != '—'
              AND TRIM(award_winner_name) != ''
        )
        SELECT
            MODE() WITHIN GROUP (ORDER BY award_winner_name) AS display_name,
            norm_name,
            COUNT(*) AS contracts_won,
            COALESCE(SUM(award_value), 0) AS total_value,
            COALESCE(AVG(award_value) FILTER (WHERE award_value IS NOT NULL), 0) AS avg_value,
            MIN(award_date) AS first_award,
            MAX(award_date) AS last_award,
            COUNT(DISTINCT award_winner_name) AS name_variants
        FROM norm
        WHERE norm_name != ''
        GROUP BY norm_name
        ORDER BY contracts_won DESC, total_value DESC
        LIMIT :limit
    """), params).mappings().all()

    return [
        {
            "name": r["display_name"],
            "contracts_won": r["contracts_won"],
            "total_value_eur": float(r["total_value"]),
            "avg_value_eur": round(float(r["avg_value"]), 2),
            "first_award": str(r["first_award"]) if r["first_award"] else None,
            "last_award": str(r["last_award"]) if r["last_award"] else None,
            "name_variants": r["name_variants"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 3. Top pouvoirs adjudicateurs (contracting authorities)
# ---------------------------------------------------------------------------

def get_top_buyers(
    db: Session, cpv_groups: list[str], limit: int = 20,
) -> list[dict[str, Any]]:
    """Top contracting authorities in this CPV group.

    Only shows reliably available data: notice count and type breakdown.
    Award values are NOT shown per buyer because CN and CAN are separate
    records that may have different organisation_names, making the join
    unreliable.
    """
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "limit": limit}

    rows = db.execute(text(f"""
        SELECT
            COALESCE(
                (SELECT value FROM jsonb_each_text(organisation_names::jsonb)
                 WHERE key IN ('fr', 'fra', 'FR') LIMIT 1),
                (SELECT value FROM jsonb_each_text(organisation_names::jsonb) LIMIT 1),
                organisation_id,
                'Inconnu'
            ) AS buyer_name,
            COUNT(*) AS notice_count,
            COUNT(CASE WHEN notice_type ILIKE '%cn%'
                       OR notice_type ILIKE '%contract notice%'
                       OR form_type ILIKE '%competition%'
                       THEN 1 END) AS cn_count,
            COUNT(CASE WHEN notice_type ILIKE '%can%'
                       OR notice_type ILIKE '%award%'
                       OR notice_type ILIKE '%result%'
                       THEN 1 END) AS can_count,
            COUNT(CASE WHEN deadline > NOW() THEN 1 END) AS active_count
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND organisation_names IS NOT NULL
          AND jsonb_typeof(organisation_names::jsonb) = 'object'
        GROUP BY buyer_name
        ORDER BY notice_count DESC
        LIMIT :limit
    """), params).mappings().all()

    return [
        {
            "name": r["buyer_name"],
            "notice_count": r["notice_count"],
            "cn_count": r["cn_count"],
            "can_count": r["can_count"],
            "active_count": r["active_count"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 4. Niveau de concurrence (competition level)
# ---------------------------------------------------------------------------

def get_competition(
    db: Session, cpv_groups: list[str],
) -> dict[str, Any]:
    """Competition analysis: tender count distribution."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = _cpv_params(cpv_groups)

    # Average + distribution
    stats = db.execute(text(f"""
        SELECT
            COUNT(*) AS total_with_tenders,
            AVG(number_tenders_received) AS avg_tenders,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY number_tenders_received) AS median_tenders,
            MIN(number_tenders_received) AS min_tenders,
            MAX(number_tenders_received) AS max_tenders,
            COUNT(CASE WHEN number_tenders_received = 1 THEN 1 END) AS single_bid,
            COUNT(CASE WHEN number_tenders_received BETWEEN 2 AND 3 THEN 1 END) AS low_competition,
            COUNT(CASE WHEN number_tenders_received BETWEEN 4 AND 6 THEN 1 END) AS medium_competition,
            COUNT(CASE WHEN number_tenders_received BETWEEN 7 AND 10 THEN 1 END) AS high_competition,
            COUNT(CASE WHEN number_tenders_received > 10 THEN 1 END) AS very_high_competition
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND number_tenders_received IS NOT NULL
          AND number_tenders_received > 0
    """), params).mappings().first()

    total = stats["total_with_tenders"] or 1  # avoid div/0

    return {
        "total_with_data": stats["total_with_tenders"],
        "avg_tenders": round(float(stats["avg_tenders"] or 0), 1),
        "median_tenders": round(float(stats["median_tenders"] or 0), 1),
        "min_tenders": stats["min_tenders"],
        "max_tenders": stats["max_tenders"],
        "distribution": [
            {"label": "1 offre (sans concurrence)", "count": stats["single_bid"],
             "pct": round(stats["single_bid"] / total * 100, 1)},
            {"label": "2-3 offres", "count": stats["low_competition"],
             "pct": round(stats["low_competition"] / total * 100, 1)},
            {"label": "4-6 offres", "count": stats["medium_competition"],
             "pct": round(stats["medium_competition"] / total * 100, 1)},
            {"label": "7-10 offres", "count": stats["high_competition"],
             "pct": round(stats["high_competition"] / total * 100, 1)},
            {"label": "10+ offres", "count": stats["very_high_competition"],
             "pct": round(stats["very_high_competition"] / total * 100, 1)},
        ],
    }


# ---------------------------------------------------------------------------
# 5. Types de procédures
# ---------------------------------------------------------------------------

def get_procedure_types(
    db: Session, cpv_groups: list[str],
) -> list[dict[str, Any]]:
    """Breakdown by procedure / form type."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = _cpv_params(cpv_groups)

    rows = db.execute(text(f"""
        SELECT
            COALESCE(form_type, notice_type, 'Non spécifié') AS proc_type,
            COUNT(*) AS cnt
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
        GROUP BY proc_type
        ORDER BY cnt DESC
    """), params).mappings().all()

    total = sum(r["cnt"] for r in rows) or 1

    return [
        {
            "type": r["proc_type"],
            "count": r["cnt"],
            "pct": round(r["cnt"] / total * 100, 1),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 6. Répartition géographique (NUTS codes)
# ---------------------------------------------------------------------------

# NUTS code → region label (Belgium + major EU)
NUTS_LABELS: dict[str, str] = {
    "BE1": "Bruxelles-Capitale",
    "BE10": "Bruxelles-Capitale",
    "BE2": "Flandre",
    "BE21": "Anvers",
    "BE22": "Limbourg",
    "BE23": "Flandre orientale",
    "BE24": "Brabant flamand",
    "BE25": "Flandre occidentale",
    "BE3": "Wallonie",
    "BE31": "Brabant wallon",
    "BE32": "Hainaut",
    "BE33": "Liège",
    "BE34": "Luxembourg (BE)",
    "BE35": "Namur",
    "FR": "France",
    "NL": "Pays-Bas",
    "DE": "Allemagne",
    "LU": "Luxembourg",
    "IT": "Italie",
    "ES": "Espagne",
}


def get_geography(
    db: Session, cpv_groups: list[str], limit: int = 20,
) -> list[dict[str, Any]]:
    """Geographic distribution by NUTS codes."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "limit": limit}

    # NUTS codes are stored as JSON arrays, so we unnest them
    rows = db.execute(text(f"""
        SELECT
            nuts_code,
            COUNT(*) AS cnt
        FROM (
            SELECT jsonb_array_elements_text(nuts_codes::jsonb) AS nuts_code
            FROM notices
            WHERE {cpv_clause}
              AND cpv_main_code IS NOT NULL
              AND nuts_codes IS NOT NULL
              AND jsonb_typeof(nuts_codes::jsonb) = 'array'
        ) sub
        GROUP BY nuts_code
        ORDER BY cnt DESC
        LIMIT :limit
    """), params).mappings().all()

    return [
        {
            "nuts_code": r["nuts_code"],
            "label": _nuts_label(r["nuts_code"]),
            "count": r["cnt"],
        }
        for r in rows
    ]


def _nuts_label(code: str) -> str:
    """Resolve NUTS code to human label, trying progressively shorter prefixes."""
    if code in NUTS_LABELS:
        return NUTS_LABELS[code]
    if len(code) >= 4 and code[:4] in NUTS_LABELS:
        return NUTS_LABELS[code[:4]]
    if len(code) >= 3 and code[:3] in NUTS_LABELS:
        return NUTS_LABELS[code[:3]]
    if len(code) >= 2 and code[:2] in NUTS_LABELS:
        return NUTS_LABELS[code[:2]]
    return code


# ---------------------------------------------------------------------------
# 7. Saisonnalité (monthly patterns)
# ---------------------------------------------------------------------------

def get_seasonality(
    db: Session, cpv_groups: list[str],
) -> list[dict[str, Any]]:
    """Average monthly publication pattern (across all years)."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = _cpv_params(cpv_groups)

    rows = db.execute(text(f"""
        SELECT
            EXTRACT(MONTH FROM publication_date)::INTEGER AS month_num,
            COUNT(*) AS total_notices,
            COUNT(DISTINCT EXTRACT(YEAR FROM publication_date)) AS year_span,
            ROUND(COUNT(*)::NUMERIC /
                  GREATEST(COUNT(DISTINCT EXTRACT(YEAR FROM publication_date)), 1), 1
            ) AS avg_per_year
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND publication_date IS NOT NULL
        GROUP BY month_num
        ORDER BY month_num
    """), params).mappings().all()

    month_names_fr = [
        "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
    ]

    return [
        {
            "month": r["month_num"],
            "month_name": month_names_fr[r["month_num"]] if r["month_num"] <= 12 else "?",
            "total": r["total_notices"],
            "avg_per_year": float(r["avg_per_year"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 8. Distribution des montants (value buckets)
# ---------------------------------------------------------------------------

def get_value_distribution(
    db: Session, cpv_groups: list[str],
) -> dict[str, Any]:
    """Distribution of contract values in buckets."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = _cpv_params(cpv_groups)

    # Estimated values
    estimated = db.execute(text(f"""
        SELECT
            COUNT(CASE WHEN estimated_value < 50000 THEN 1 END) AS under_50k,
            COUNT(CASE WHEN estimated_value >= 50000 AND estimated_value < 200000 THEN 1 END) AS r_50k_200k,
            COUNT(CASE WHEN estimated_value >= 200000 AND estimated_value < 1000000 THEN 1 END) AS r_200k_1m,
            COUNT(CASE WHEN estimated_value >= 1000000 AND estimated_value < 5000000 THEN 1 END) AS r_1m_5m,
            COUNT(CASE WHEN estimated_value >= 5000000 THEN 1 END) AS over_5m,
            COUNT(*) AS total
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND estimated_value IS NOT NULL
          AND estimated_value > 0
    """), params).mappings().first()

    # Award values
    awarded = db.execute(text(f"""
        SELECT
            COUNT(CASE WHEN award_value < 50000 THEN 1 END) AS under_50k,
            COUNT(CASE WHEN award_value >= 50000 AND award_value < 200000 THEN 1 END) AS r_50k_200k,
            COUNT(CASE WHEN award_value >= 200000 AND award_value < 1000000 THEN 1 END) AS r_200k_1m,
            COUNT(CASE WHEN award_value >= 1000000 AND award_value < 5000000 THEN 1 END) AS r_1m_5m,
            COUNT(CASE WHEN award_value >= 5000000 THEN 1 END) AS over_5m,
            COUNT(*) AS total
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND award_value IS NOT NULL
          AND award_value > 0
    """), params).mappings().first()

    def _buckets(row):
        total = row["total"] or 1
        return [
            {"label": "< 50K€", "count": row["under_50k"],
             "pct": round(row["under_50k"] / total * 100, 1)},
            {"label": "50K - 200K€", "count": row["r_50k_200k"],
             "pct": round(row["r_50k_200k"] / total * 100, 1)},
            {"label": "200K - 1M€", "count": row["r_200k_1m"],
             "pct": round(row["r_200k_1m"] / total * 100, 1)},
            {"label": "1M - 5M€", "count": row["r_1m_5m"],
             "pct": round(row["r_1m_5m"] / total * 100, 1)},
            {"label": "> 5M€", "count": row["over_5m"],
             "pct": round(row["over_5m"] / total * 100, 1)},
        ]

    return {
        "estimated": {"total_with_value": estimated["total"], "buckets": _buckets(estimated)},
        "awarded": {"total_with_value": awarded["total"], "buckets": _buckets(awarded)},
    }


# ---------------------------------------------------------------------------
# 9. Marchés sans concurrence (single-bid contracts)
# ---------------------------------------------------------------------------

def get_single_bid_contracts(
    db: Session, cpv_groups: list[str], limit: int = 20,
) -> dict[str, Any]:
    """Recent contracts won with a single bid — low competition opportunities."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "limit": limit}

    # Count
    count = db.execute(text(f"""
        SELECT COUNT(*) FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND number_tenders_received = 1
          AND award_winner_name IS NOT NULL AND award_winner_name != '—'
    """), _cpv_params(cpv_groups)).scalar() or 0

    # Recent examples
    rows = db.execute(text(f"""
        SELECT
            id, title, award_winner_name, award_value, award_date,
            source, organisation_names, estimated_value
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND number_tenders_received = 1
          AND award_winner_name IS NOT NULL AND award_winner_name != '—'
        ORDER BY COALESCE(award_date, publication_date) DESC NULLS LAST
        LIMIT :limit
    """), params).mappings().all()

    return {
        "total_single_bid": count,
        "recent": [
            {
                "id": r["id"],
                "title": (r["title"] or "")[:120],
                "winner": r["award_winner_name"],
                "award_value_eur": float(r["award_value"]) if r["award_value"] else None,
                "estimated_value_eur": float(r["estimated_value"]) if r["estimated_value"] else None,
                "award_date": str(r["award_date"]) if r["award_date"] else None,
                "source": r["source"],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# 10. Délai moyen d'attribution (publication → award timeline)
# ---------------------------------------------------------------------------

def get_award_timeline(
    db: Session, cpv_groups: list[str],
) -> dict[str, Any]:
    """Average time from publication to award in this sector."""
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = _cpv_params(cpv_groups)

    stats = db.execute(text(f"""
        SELECT
            COUNT(*) AS total,
            AVG(award_date - publication_date) AS avg_days,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY award_date - publication_date) AS median_days,
            MIN(award_date - publication_date) AS min_days,
            MAX(award_date - publication_date) AS max_days,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY award_date - publication_date) AS p25_days,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY award_date - publication_date) AS p75_days
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND publication_date IS NOT NULL
          AND award_date IS NOT NULL
          AND award_date > publication_date
    """), params).mappings().first()

    return {
        "total_with_data": stats["total"],
        "avg_days": round(float(stats["avg_days"])) if stats["avg_days"] else None,
        "median_days": round(float(stats["median_days"])) if stats["median_days"] else None,
        "min_days": int(stats["min_days"].days) if stats["min_days"] else None,
        "max_days": int(stats["max_days"].days) if stats["max_days"] else None,
        "p25_days": round(float(stats["p25_days"])) if stats["p25_days"] else None,
        "p75_days": round(float(stats["p75_days"])) if stats["p75_days"] else None,
    }


# ---------------------------------------------------------------------------
# 11. Opportunités en cours (active notices)
# ---------------------------------------------------------------------------

def get_active_opportunities(
    db: Session, cpv_groups: list[str], limit: int = 20,
) -> dict[str, Any]:
    """Active notices (deadline in the future) for the selected CPV groups."""
    now = datetime.now(timezone.utc)
    cpv_clause = _cpv_filter_clause(cpv_groups)
    params = {**_cpv_params(cpv_groups), "now": now, "limit": limit}

    # Count
    count = db.execute(text(f"""
        SELECT COUNT(*) FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND deadline > :now
    """), {**_cpv_params(cpv_groups), "now": now}).scalar() or 0

    # Nearest deadlines
    rows = db.execute(text(f"""
        SELECT
            id, title, source, deadline, estimated_value,
            cpv_main_code, organisation_names, url,
            EXTRACT(EPOCH FROM (deadline - :now)) / 86400 AS days_left
        FROM notices
        WHERE {cpv_clause}
          AND cpv_main_code IS NOT NULL
          AND deadline > :now
        ORDER BY deadline ASC
        LIMIT :limit
    """), params).mappings().all()

    def _org_name(org_names):
        if not org_names or not isinstance(org_names, dict):
            return None
        for key in ("fr", "fra", "FR", "nl", "nld", "NL", "en", "eng", "EN"):
            if key in org_names:
                return org_names[key]
        return next(iter(org_names.values()), None)

    return {
        "total_active": count,
        "notices": [
            {
                "id": r["id"],
                "title": (r["title"] or "")[:150],
                "source": r["source"],
                "deadline": r["deadline"].isoformat() if r["deadline"] else None,
                "days_left": round(float(r["days_left"]), 1) if r["days_left"] else None,
                "estimated_value_eur": float(r["estimated_value"]) if r["estimated_value"] else None,
                "cpv_code": r["cpv_main_code"],
                "buyer": _org_name(r["organisation_names"]),
                "url": r["url"],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Full analysis (combines all 11 sections)
# ---------------------------------------------------------------------------

def get_full_cpv_analysis(
    db: Session,
    cpv_groups: list[str],
    months: int = 24,
    top_limit: int = 20,
) -> dict[str, Any]:
    """Run all 11 analysis sections for the given CPV groups.

    Returns a comprehensive dict with all sections.
    """
    labels = [{"code": g, "label": cpv_group_label(g)} for g in cpv_groups]

    logger.info(
        "[CPV Intelligence] Full analysis for %s (%d months, top %d)",
        cpv_groups, months, top_limit,
    )

    result: dict[str, Any] = {
        "cpv_groups": labels,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Each section is wrapped in try/except so one failure doesn't break everything
    sections = {
        "volume_value": lambda: get_volume_value(db, cpv_groups, months),
        "top_winners": lambda: get_top_winners(db, cpv_groups, top_limit),
        "top_buyers": lambda: get_top_buyers(db, cpv_groups, top_limit),
        "competition": lambda: get_competition(db, cpv_groups),
        "procedure_types": lambda: get_procedure_types(db, cpv_groups),
        "geography": lambda: get_geography(db, cpv_groups, top_limit),
        "seasonality": lambda: get_seasonality(db, cpv_groups),
        "value_distribution": lambda: get_value_distribution(db, cpv_groups),
        "single_bid_contracts": lambda: get_single_bid_contracts(db, cpv_groups, top_limit),
        "award_timeline": lambda: get_award_timeline(db, cpv_groups),
        "active_opportunities": lambda: get_active_opportunities(db, cpv_groups, top_limit),
    }

    for name, fn in sections.items():
        try:
            result[name] = fn()
        except Exception as e:
            logger.exception("[CPV Intelligence] Section '%s' failed: %s", name, e)
            result[name] = {"error": str(e)}

    return result
