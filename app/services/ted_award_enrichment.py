"""
TED CAN Award Enrichment Service.

Re-fetches TED CAN notices that have country-code-only winner names (e.g. "BEL", "FR")
with expanded search fields to get the actual company name.

This fixes the gap where DEFAULT_FIELDS didn't include 'organisation-name-tenderer'
and 'received-submissions-type-val', causing fallback to winner-country.
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


def _is_country_code_only(name: str | None) -> bool:
    """Check if winner name is just a country code (the fallback we want to fix)."""
    if not name:
        return False
    return bool(COUNTRY_CODE_RE.match(name.strip()))


def enrich_ted_can_batch(
    db: Session,
    limit: int = 500,
    batch_size: int = 10,
    api_delay_ms: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Re-fetch TED CANs that have country-code-only winner names.

    Strategy:
      1. Find TED notices where award_winner_name matches country code pattern
      2. For each, re-search TED by publication-number with expanded fields
      3. Re-parse award fields using the updated mapping
      4. Update the notice record

    Returns stats dict.
    """
    from app.connectors.ted.client import search_ted_notices
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
    }

    # ── 1. Find candidates: TED notices with country-code winner names ──
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

    # ── 2. Process in batches ──
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]

        for notice in batch:
            pub_number = notice.source_id  # e.g. "123456-2024"
            old_winner = notice.award_winner_name

            if dry_run:
                logger.info(
                    "[TED enrich DRY] %s: winner='%s' → would re-fetch",
                    pub_number, old_winner,
                )
                stats["skipped_dry_run"] += 1
                continue

            # Search TED for this specific publication number
            try:
                search_term = f'publication-number = "{pub_number}"'
                result = search_ted_notices(
                    term=search_term, page=1, page_size=1,
                )
                items = result.get("notices", [])
            except Exception as e:
                logger.warning("[TED enrich] API error for %s: %s", pub_number, e)
                stats["api_errors"] += 1
                time.sleep(api_delay_ms / 1000)
                continue

            if not items:
                logger.debug("[TED enrich] %s: not found in TED search", pub_number)
                stats["not_found"] += 1
                time.sleep(api_delay_ms / 1000)
                continue

            item = items[0]

            # ── 3. Re-extract award fields with the expanded data ──
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
                logger.debug(
                    "[TED enrich] %s: still country-code '%s' after re-fetch",
                    pub_number, new_winner,
                )
                stats["still_country_only"] += 1
            else:
                # Update the notice
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

                logger.info(
                    "[TED enrich] %s: '%s' → '%s' (value=%s, tenders=%s)",
                    pub_number, old_winner, new_winner, new_value, new_tenders,
                )
                stats["enriched"] += 1

            time.sleep(api_delay_ms / 1000)

        # Commit after each batch
        if not dry_run:
            db.commit()
            logger.info(
                "[TED enrich] Batch %d-%d committed (%d enriched so far)",
                i + 1, min(i + batch_size, len(candidates)), stats["enriched"],
            )

    logger.info(
        "[TED enrich] Done: %d candidates, %d enriched, %d still country-only, %d errors",
        stats["total_candidates"], stats["enriched"],
        stats["still_country_only"], stats["api_errors"],
    )
    return stats
