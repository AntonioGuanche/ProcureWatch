"""BOSA CAN award enrichment via workspace API.

Reusable service for enriching Contract Award Notices with award data
(winner, value, date, tenders) by fetching eForms XML from the
BOSA publication-workspace detail endpoint.

Used by:
- bulk_import pipeline (daily auto-enrichment)
- admin bulk-enrich endpoint (backfill historical data)
"""
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def enrich_bosa_can_batch(
    db: Session,
    limit: int = 500,
    batch_size: int = 50,
    api_delay_ms: int = 300,
) -> dict[str, Any]:
    """
    Enrich BOSA CANs (notice_sub_type=29) that lack award data.

    For each eligible CAN:
      1. Check if raw_data already has XML → parse directly
      2. Else: GET /publication-workspaces/{source_id} → workspace detail
      3. Parse eForms XML for award fields
      4. UPDATE notice with award fields + full workspace as raw_data

    Args:
        db: SQLAlchemy session
        limit: Max notices to process (default 500 for daily runs)
        batch_size: Commit interval
        api_delay_ms: Milliseconds between API calls (rate limiting)

    Returns:
        Stats dict with enriched/skipped/error counts
    """
    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Count eligible
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '')"
    ))
    total_eligible = count_result.scalar() or 0

    if total_eligible == 0:
        return {"total_eligible": 0, "enriched": 0, "message": "No CANs to enrich"}

    # Initialize BOSA API client
    workspace_client = _get_workspace_client()
    if workspace_client is None:
        logger.warning("[BOSA Enrich] Cannot init workspace client, skipping API enrichment")
        # Still try to parse existing XML in raw_data
        pass

    stats = {
        "total_eligible": total_eligible,
        "enriched": 0,
        "skipped_no_xml": 0,
        "skipped_no_fields": 0,
        "api_errors": 0,
        "parse_errors": 0,
        "already_has_xml": 0,
        "batches": 0,
    }

    delay_sec = api_delay_ms / 1000.0
    processed = 0
    offset = 0

    while processed < limit:
        rows = db.execute(text(
            "SELECT id, source_id, raw_data FROM notices "
            "WHERE source = 'BOSA_EPROC' "
            "  AND notice_sub_type = '29' "
            "  AND raw_data IS NOT NULL "
            "  AND (award_winner_name IS NULL OR award_winner_name = '') "
            "ORDER BY publication_date DESC, id "
            "LIMIT :batch_size OFFSET :offset"
        ), {"batch_size": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        for row in rows:
            if processed >= limit:
                break

            notice_id, source_id, raw_data = row[0], row[1], row[2]
            processed += 1

            try:
                if not isinstance(raw_data, dict):
                    raw_data = json.loads(raw_data) if raw_data else {}

                # Step 1: Check if raw_data already has XML
                existing_xml = extract_xml_from_raw_data(raw_data)
                if existing_xml:
                    parsed = parse_award_data(existing_xml)
                    fields = build_notice_fields(parsed)
                    if fields:
                        _update_notice_fields(db, notice_id, fields)
                        stats["enriched"] += 1
                    else:
                        stats["skipped_no_fields"] += 1
                    stats["already_has_xml"] += 1
                    continue

                # Step 2: Fetch workspace detail via API
                if not source_id or workspace_client is None:
                    stats["skipped_no_xml"] += 1
                    continue

                time.sleep(delay_sec)
                workspace_data = workspace_client.get_publication_workspace(source_id)

                if not workspace_data:
                    stats["api_errors"] += 1
                    continue

                # Step 3: Extract + parse XML
                xml_content = extract_xml_from_raw_data(workspace_data)
                if not xml_content:
                    stats["skipped_no_xml"] += 1
                    continue

                parsed = parse_award_data(xml_content)
                fields = build_notice_fields(parsed)

                if not fields:
                    stats["skipped_no_fields"] += 1
                    continue

                # Step 4: Update notice + replace raw_data with full workspace
                _update_notice_fields(db, notice_id, fields)
                db.execute(
                    text("UPDATE notices SET raw_data = :rd WHERE id = :nid"),
                    {"rd": json.dumps(workspace_data, default=str), "nid": notice_id},
                )
                stats["enriched"] += 1

            except Exception as e:
                logger.warning(
                    "BOSA CAN enrichment error for %s (source=%s): %s",
                    notice_id, source_id, e,
                )
                stats["parse_errors"] += 1

        db.commit()
        stats["batches"] += 1
        offset += batch_size

    logger.info(
        "[BOSA Enrich] Done: %d enriched, %d errors, %d eligible remaining",
        stats["enriched"], stats["parse_errors"] + stats["api_errors"],
        total_eligible - stats["enriched"],
    )
    return stats


def _get_workspace_client():
    """Try to get BOSA official client for workspace fetches."""
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, provider = _get_client()
        if isinstance(client, OfficialEProcurementClient):
            return client
        logger.warning("[BOSA Enrich] Client is %s, not official — cannot fetch workspaces", provider)
    except Exception as e:
        logger.warning("[BOSA Enrich] Cannot init BOSA client: %s", e)
    return None


def _update_notice_fields(db: Session, notice_id: str, fields: dict[str, Any]):
    """Update a single notice with parsed award fields."""
    set_clauses = []
    params: dict[str, Any] = {"nid": notice_id}

    if "award_winner_name" in fields:
        set_clauses.append("award_winner_name = :winner")
        params["winner"] = fields["award_winner_name"]
    if "award_value" in fields:
        set_clauses.append("award_value = :value")
        params["value"] = float(fields["award_value"])
    if "award_date" in fields:
        set_clauses.append("award_date = :adate")
        params["adate"] = str(fields["award_date"])
    if "number_tenders_received" in fields:
        set_clauses.append("number_tenders_received = :ntenders")
        params["ntenders"] = fields["number_tenders_received"]
    if "award_criteria_json" in fields:
        set_clauses.append("award_criteria_json = :acjson")
        params["acjson"] = json.dumps(fields["award_criteria_json"], default=str)

    if set_clauses:
        set_clauses.append("updated_at = now()")
        sql = f"UPDATE notices SET {', '.join(set_clauses)} WHERE id = :nid"
        db.execute(text(sql), params)
