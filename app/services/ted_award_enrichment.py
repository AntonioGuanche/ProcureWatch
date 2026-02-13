"""
TED CAN Award Enrichment Service.

Re-fetches TED CAN notices that have country-code-only winner names (e.g. "BEL", "FR")
with expanded search fields to get the actual company name.

v2: Batch API calls — 50 publication numbers per TED query instead of 1-by-1.
    500 notices now takes ~30s instead of ~12 min.
"""
import logging
import re
import time
from typing import Any

from sqlalchemy import func
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

    Returns dict mapping publication-number -> item dict.
    """
    from app.connectors.ted.client import search_ted_notices

    if not pub_numbers:
        return {}

    # Build OR query: ND = "123-2024" OR ND = "456-2024" OR ...
    # ND is the TED shorthand for publication-number
    clauses = [f'ND = "{pn}"' for pn in pub_numbers]
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
        if pn:
            result_map[str(pn)] = item

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

    v2 strategy (batch):
      1. Find TED notices where award_winner_name matches country code pattern
      2. Batch-fetch from TED API (50 per call instead of 1-by-1)
      3. Re-parse award fields using the updated mapping
      4. Update the notice records

    Returns stats dict.
    """
    from app.services.notice_service import (
        _safe_str, _safe_decimal, _safe_date, _safe_int,
        _ted_pick_text, _extract_award_criteria,
    )

    stats: dict[str, Any] = {
        "total_candidates": 0,
        "enriched": 0,
        "still_country_only": 0,
        "api_errors": 0,
        "not_found": 0,
        "skipped_dry_run": 0,
        "api_calls": 0,
    }

    # -- 1. Find candidates: TED notices with country-code winner names --
    candidates = (
        db.query(ProcurementNotice)
        .filter(
            ProcurementNotice.source == "TED_EU",
            ProcurementNotice.award_winner_name.isnot(None),
            ProcurementNotice.award_winner_name != "",
            # Country codes are 2-3 chars; real company names are longer
            func.length(ProcurementNotice.award_winner_name) <= 3,
        )
        .limit(limit)
        .all()
    )

    stats["total_candidates"] = len(candidates)
    if not candidates:
        logger.info("[TED enrich] No candidates found with country-code-only winners")
        return stats

    logger.info(
        "[TED enrich] Found %d TED CANs with country-code winners to re-enrich",
        len(candidates),
    )

    if dry_run:
        stats["skipped_dry_run"] = len(candidates)
        return stats

    # -- 2. Build lookup: source_id -> notice --
    notice_map: dict[str, ProcurementNotice] = {}
    for n in candidates:
        if n.source_id:
            notice_map[n.source_id] = n

    # -- 3. Batch-fetch from TED API (BATCH_QUERY_SIZE at a time) --
    all_pub_numbers = list(notice_map.keys())

    for chunk_start in range(0, len(all_pub_numbers), BATCH_QUERY_SIZE):
        chunk = all_pub_numbers[chunk_start : chunk_start + BATCH_QUERY_SIZE]
        stats["api_calls"] += 1

        logger.info(
            "[TED enrich] Batch %d: fetching %d pub numbers...",
            stats["api_calls"], len(chunk),
        )

        result_map = _batch_fetch_ted(chunk, api_delay_ms=api_delay_ms)

        if not result_map:
            stats["api_errors"] += 1

        # -- 4. Process results --
        for pub_number in chunk:
            notice = notice_map[pub_number]
            item = result_map.get(pub_number)

            if not item:
                stats["not_found"] += 1
                continue

            # Re-extract award fields with the expanded data
            new_winner = _safe_str(
                _ted_pick_text(item.get("business-name"))
                or _ted_pick_text(item.get("winner-name"))
                or _ted_pick_text(item.get("organisation-name-tenderer"))
                or _ted_pick_text(item.get("organisation-partname-tenderer"))
                or _ted_pick_text(item.get("winner-country")),
                500,
            )

            new_value = _safe_decimal(
                item.get("tender-value")
                or item.get("total-value")
                or item.get("tender-value-cur")
                or item.get("result-value-lot")
                or item.get("contract-value-lot")
            )

            new_date = _safe_date(
                item.get("winner-decision-date")
                or item.get("award-date")
            )

            new_tenders = _safe_int(
                item.get("received-submissions-type-val")
                or item.get("number-of-tenders")
            )

            new_criteria = _extract_award_criteria(item)

            # Check if we actually got a better name
            if _is_country_code_only(new_winner):
                stats["still_country_only"] += 1
            else:
                if new_winner:
                    notice.award_winner_name = new_winner
                if new_value is not None:
                    notice.award_value = new_value
                if new_date is not None:
                    notice.award_date = new_date
                if new_tenders is not None:
                    notice.number_tenders_received = new_tenders
                if new_criteria is not None:
                    notice.award_criteria_json = new_criteria

                # Also update raw_data with the fresh search result
                notice.raw_data = item

                stats["enriched"] += 1

        # Commit after each batch of API calls
        db.commit()
        logger.info(
            "[TED enrich] After batch %d: %d enriched, %d not found, %d still country-only",
            stats["api_calls"], stats["enriched"], stats["not_found"], stats["still_country_only"],
        )

    logger.info(
        "[TED enrich] Done: %d candidates, %d enriched, %d still country-only, "
        "%d not found, %d API calls",
        stats["total_candidates"], stats["enriched"],
        stats["still_country_only"], stats["not_found"], stats["api_calls"],
    )
    return stats
