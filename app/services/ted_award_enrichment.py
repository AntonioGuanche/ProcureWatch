"""
TED CAN Award Enrichment Service.

Re-fetches TED CAN notices that have country-code-only winner names (e.g. "BEL", "FR")
with expanded search fields to get the actual company name.

v3: Batch API calls + SQL UPDATE to fix ALL duplicates of same source_id.
    Fixes infinite loop where only 1 of N duplicate rows was updated per pass.
"""
import json
import logging
import re
import time
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.notice import ProcurementNotice

logger = logging.getLogger(__name__)

# Pattern matching ISO 3166-1 alpha-2/3 country codes (2-3 uppercase letters)
COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2,3}$")

# How many publication numbers to batch per TED API call
BATCH_QUERY_SIZE = 50


def _is_country_code_only(name: str | None) -> bool:
    """Check if winner name is just a country code (the fallback we want to fix)."""
    if not name:
        return False
    return bool(COUNTRY_CODE_RE.match(name.strip()))


def _batch_fetch_ted(pub_numbers: list[str], api_delay_ms: int = 300) -> dict[str, dict]:
    """Fetch multiple TED notices in one API call using OR query.

    Uses full field name 'publication-number' (not ND alias) for guaranteed compat.
    Returns dict mapping publication-number -> item dict.
    """
    from app.connectors.ted.client import search_ted_notices

    if not pub_numbers:
        return {}

    # Build OR query with full field name (proven to work)
    clauses = [f'publication-number = "{pn}"' for pn in pub_numbers]
    query = " OR ".join(clauses)

    try:
        result = search_ted_notices(
            term=query,
            page=1,
            page_size=min(len(pub_numbers), 250),
        )
        items = result.get("notices", [])
    except Exception as e:
        logger.warning("[TED enrich batch] API error for %d numbers: %s", len(pub_numbers), e)
        time.sleep(api_delay_ms / 1000)
        return {}

    # Index by publication-number for fast lookup
    result_map: dict[str, dict] = {}
    for item in items:
        pn = item.get("publication-number")
        if isinstance(pn, list):
            pn = pn[0] if pn else None
        if isinstance(pn, dict):
            pn = pn.get("value") or pn.get("text")
        if pn:
            result_map[str(pn).strip()] = item

    logger.info(
        "[TED enrich batch] Queried %d pub numbers, got %d results back",
        len(pub_numbers), len(result_map),
    )
    time.sleep(api_delay_ms / 1000)
    return result_map


def enrich_ted_can_batch(
    db: Session,
    limit: int = 500,
    batch_size: int = 10,  # kept for API compat but ignored internally
    api_delay_ms: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Re-fetch TED CANs that have country-code-only winner names.

    v3 strategy:
      1. Find DISTINCT source_ids where award_winner_name is a country code
      2. Batch-fetch from TED API (50 per call)
      3. SQL UPDATE all rows with that source_id (fixes duplicates)

    Returns stats dict.
    """
    from app.services.notice_service import (
        _safe_str, _safe_decimal, _safe_date, _safe_int,
        _ted_pick_text, _extract_award_criteria,
    )

    stats: dict[str, Any] = {
        "total_candidates": 0,
        "distinct_source_ids": 0,
        "enriched": 0,
        "rows_updated": 0,
        "still_country_only": 0,
        "api_errors": 0,
        "not_found": 0,
        "skipped_dry_run": 0,
        "api_calls": 0,
    }

    # -- 1a. Count TOTAL remaining (no LIMIT) for monitoring --
    total_remaining = db.execute(text("""
        SELECT COUNT(DISTINCT source_id)
        FROM notices
        WHERE source = 'TED_EU'
          AND award_winner_name IS NOT NULL
          AND award_winner_name != ''
          AND LENGTH(award_winner_name) <= 3
          AND source_id IS NOT NULL
    """)).scalar() or 0

    logger.info("[TED enrich] Total remaining distinct source_ids: %d", total_remaining)

    # -- 1b. Find DISTINCT source_ids with country-code winners --
    rows = db.execute(text("""
        SELECT DISTINCT source_id
        FROM notices
        WHERE source = 'TED_EU'
          AND award_winner_name IS NOT NULL
          AND award_winner_name != ''
          AND LENGTH(award_winner_name) <= 3
          AND source_id IS NOT NULL
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    distinct_ids = [r[0] for r in rows if r[0]]
    stats["total_candidates"] = len(distinct_ids)
    stats["distinct_source_ids"] = len(distinct_ids)
    stats["total_remaining_before"] = total_remaining

    if not distinct_ids:
        logger.info("[TED enrich] No candidates found with country-code-only winners")
        return stats

    logger.info(
        "[TED enrich] Found %d distinct source_ids to re-enrich",
        len(distinct_ids),
    )

    if dry_run:
        stats["skipped_dry_run"] = len(distinct_ids)
        return stats

    # -- 2. Batch-fetch from TED API --
    for chunk_start in range(0, len(distinct_ids), BATCH_QUERY_SIZE):
        chunk = distinct_ids[chunk_start : chunk_start + BATCH_QUERY_SIZE]
        stats["api_calls"] += 1

        logger.info(
            "[TED enrich] Batch API call %d: fetching %d pub numbers...",
            stats["api_calls"], len(chunk),
        )

        result_map = _batch_fetch_ted(chunk, api_delay_ms=api_delay_ms)

        if not result_map and len(chunk) > 0:
            stats["api_errors"] += 1

        # -- 3. SQL UPDATE all rows per source_id --
        for pub_number in chunk:
            item = result_map.get(pub_number)

            if not item:
                stats["not_found"] += 1
                continue

            new_winner = _safe_str(
                _ted_pick_text(item.get("business-name"))
                or _ted_pick_text(item.get("winner-name"))
                or _ted_pick_text(item.get("organisation-name-tenderer"))
                or _ted_pick_text(item.get("organisation-partname-tenderer"))
                or _ted_pick_text(item.get("winner-country")),
                500,
            )

            if _is_country_code_only(new_winner):
                stats["still_country_only"] += 1
                continue

            # Build SET clause dynamically
            updates = {}
            if new_winner:
                updates["award_winner_name"] = new_winner

            new_value = _safe_decimal(
                item.get("tender-value")
                or item.get("total-value")
                or item.get("tender-value-cur")
                or item.get("result-value-lot")
                or item.get("contract-value-lot")
            )
            if new_value is not None:
                updates["award_value"] = str(new_value)

            new_date = _safe_date(
                item.get("winner-decision-date")
                or item.get("award-date")
            )
            if new_date is not None:
                updates["award_date"] = str(new_date)

            new_tenders = _safe_int(
                item.get("received-submissions-type-val")
                or item.get("number-of-tenders")
            )
            if new_tenders is not None:
                updates["number_tenders_received"] = new_tenders

            new_criteria = _extract_award_criteria(item)
            if new_criteria is not None:
                updates["award_criteria_json"] = json.dumps(new_criteria)

            if not updates:
                continue

            # Build and execute UPDATE for ALL rows with this source_id
            set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
            updates["raw_data_json"] = json.dumps(item, default=str)
            updates["sid"] = pub_number

            result = db.execute(text(f"""
                UPDATE notices
                SET {set_clauses}, raw_data = CAST(:raw_data_json AS jsonb)
                WHERE source = 'TED_EU'
                  AND source_id = :sid
                  AND LENGTH(COALESCE(award_winner_name, '')) <= 3
            """), updates)

            rows_affected = result.rowcount
            stats["rows_updated"] += rows_affected
            stats["enriched"] += 1

        db.commit()
        logger.info(
            "[TED enrich] After batch %d: %d source_ids enriched, %d rows updated, "
            "%d not found, %d still country-only",
            stats["api_calls"], stats["enriched"], stats["rows_updated"],
            stats["not_found"], stats["still_country_only"],
        )

    # Count remaining AFTER processing
    remaining_after = db.execute(text("""
        SELECT COUNT(DISTINCT source_id)
        FROM notices
        WHERE source = 'TED_EU'
          AND award_winner_name IS NOT NULL
          AND award_winner_name != ''
          AND LENGTH(award_winner_name) <= 3
          AND source_id IS NOT NULL
    """)).scalar() or 0
    stats["total_remaining_after"] = remaining_after

    # Verification: check one of the enriched source_ids
    if distinct_ids and stats["enriched"] > 0:
        sample_sid = distinct_ids[0]
        check = db.execute(text("""
            SELECT id, source_id, award_winner_name, LENGTH(award_winner_name)
            FROM notices
            WHERE source = 'TED_EU' AND source_id = :sid
            LIMIT 5
        """), {"sid": sample_sid}).fetchall()
        stats["verification_sample"] = [
            {"id": r[0], "source_id": r[1], "winner": r[2], "len": r[3]}
            for r in check
        ]

    logger.info(
        "[TED enrich] Done: %d distinct IDs, %d enriched, %d rows updated, "
        "remaining: %d -> %d, %d API calls",
        stats["total_candidates"], stats["enriched"], stats["rows_updated"],
        total_remaining, remaining_after, stats["api_calls"],
    )
    return stats
