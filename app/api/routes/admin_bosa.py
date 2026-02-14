"""BOSA diagnostics, awards enrichment, workspace API, XML parsing."""
import json
import logging
import time
import traceback
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import require_admin_key, rate_limit_admin
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["bosa"],
    dependencies=[Depends(require_admin_key), Depends(rate_limit_admin)],
)

# ── BOSA diagnostics & backfill ──────────────────────────────────────

@router.get("/bosa-diagnostics", tags=["admin"])
def bosa_diagnostics(db: Session = Depends(get_db)) -> dict:
    """
    Diagnostic: distribution of form_type, notice_sub_type, URL coverage,
    procedure_id coverage for BOSA notices.
    """
    from app.models.notice import ProcurementNotice as Notice
    from sqlalchemy import func

    base = db.query(func.count(Notice.id)).filter(Notice.source == "BOSA_EPROC")
    total = base.scalar()

    # form_type distribution
    form_types = (
        db.query(Notice.form_type, func.count(Notice.id))
        .filter(Notice.source == "BOSA_EPROC")
        .group_by(Notice.form_type)
        .order_by(func.count(Notice.id).desc())
        .all()
    )

    # notice_sub_type distribution
    sub_types = (
        db.query(Notice.notice_sub_type, func.count(Notice.id))
        .filter(Notice.source == "BOSA_EPROC")
        .group_by(Notice.notice_sub_type)
        .order_by(func.count(Notice.id).desc())
        .all()
    )

    # URL coverage
    has_url = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.url.isnot(None), Notice.url != ""
    ).scalar()

    # procedure_id coverage
    has_proc_id = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.procedure_id.isnot(None), Notice.procedure_id != ""
    ).scalar()

    # award fields coverage
    has_winner = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.award_winner_name.isnot(None)
    ).scalar()
    has_award_val = db.query(func.count(Notice.id)).filter(
        Notice.source == "BOSA_EPROC", Notice.award_value.isnot(None)
    ).scalar()

    return {
        "total": total,
        "form_types": {str(k): v for k, v in form_types},
        "notice_sub_types": {str(k): v for k, v in sub_types},
        "url_coverage": {"filled": has_url, "pct": round(has_url / total * 100, 1) if total else 0},
        "procedure_id_coverage": {"filled": has_proc_id, "pct": round(has_proc_id / total * 100, 1) if total else 0},
        "award_winner_name": {"filled": has_winner, "pct": round(has_winner / total * 100, 1) if total else 0},
        "award_value": {"filled": has_award_val, "pct": round(has_award_val / total * 100, 1) if total else 0},
    }


@router.post("/bosa-backfill-urls", tags=["admin"])
def bosa_backfill_urls(
    limit: int = Query(200000, ge=1, le=500000),
    dry_run: bool = Query(True),
    batch_size: int = Query(5000, ge=100, le=10000),
    db: Session = Depends(get_db),
) -> dict:
    """
    Backfill URLs for BOSA notices using raw SQL batched updates.
    URL pattern: https://publicprocurement.be/publication-workspaces/{source_id}/general
    Each batch = single UPDATE ... WHERE id IN (SELECT ... LIMIT N) → no ORM overhead.
    """
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "AND (url IS NULL OR url = '') "
        "AND source_id IS NOT NULL AND source_id != ''"
    ))
    total_missing = count_result.scalar()

    if dry_run:
        return {"updated": min(total_missing, limit), "total_missing": total_missing, "dry_run": True}

    updated = 0
    batches = 0
    errors = []

    while updated < limit:
        try:
            result = db.execute(text(
                "UPDATE notices SET "
                "  url = 'https://publicprocurement.be/publication-workspaces/' "
                "        || source_id || '/general', "
                "  updated_at = now() "
                "WHERE id IN ("
                "  SELECT id FROM notices "
                "  WHERE source = 'BOSA_EPROC' "
                "  AND (url IS NULL OR url = '') "
                "  AND source_id IS NOT NULL AND source_id != '' "
                "  LIMIT :batch_size"
                ")"
            ), {"batch_size": batch_size})
            db.commit()
            rows = result.rowcount
            if rows == 0:
                break
            updated += rows
            batches += 1
            logger.info("bosa-backfill-urls: batch %d → %d rows (total %d)",
                        batches, rows, updated)
        except Exception as e:
            db.rollback()
            errors.append(f"batch {batches}: {str(e)[:200]}")
            logger.error("bosa-backfill-urls error at batch %d: %s", batches, e)
            break

    return {
        "updated": updated,
        "total_missing": total_missing,
        "batches": batches,
        "batch_size": batch_size,
        "errors": errors if errors else None,
        "dry_run": False,
    }


# ── BOSA deep sample: explore what's really inside type 29 (CAN) ──────


@router.get("/bosa-sample-can", tags=["admin"])
def bosa_sample_can(
    limit: int = Query(3, ge=1, le=10),
    notice_sub_type: str = Query("29"),
    fetch_workspace: bool = Query(True),
    fetch_notice: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Sample BOSA notices of a given noticeSubType and explore their content:
    1. raw_data from DB (search result)
    2. /publication-workspaces/{id} detail (Dos API)
    3. /notices/{notice-id} detail (Dos API) for each noticeId
    """
    from app.models.notice import ProcurementNotice as Notice

    # Get sample notices
    notices = (
        db.query(Notice)
        .filter(
            Notice.source == "BOSA_EPROC",
            Notice.notice_sub_type == notice_sub_type,
        )
        .order_by(Notice.publication_date.desc().nulls_last())
        .limit(limit)
        .all()
    )

    if not notices:
        return {"error": f"No BOSA notices with notice_sub_type={notice_sub_type}"}

    # Try to get BOSA client for detail APIs
    workspace_client = None
    if fetch_workspace or fetch_notice:
        try:
            from app.connectors.bosa.client import _get_client
            from app.connectors.bosa.official_client import OfficialEProcurementClient
            client, provider = _get_client()
            if isinstance(client, OfficialEProcurementClient):
                workspace_client = client
            else:
                logger.warning("BOSA client is not official, can't fetch detail: %s", provider)
        except Exception as e:
            logger.warning("Failed to get BOSA client: %s", e)

    results = []
    for n in notices:
        item: dict[str, Any] = {
            "db_id": n.id,
            "source_id": n.source_id,
            "title": n.title[:120] if n.title else None,
            "notice_sub_type": n.notice_sub_type,
            "form_type": n.form_type,
            "procedure_id": n.procedure_id,
            "publication_date": str(n.publication_date) if n.publication_date else None,
            "award_winner_name": n.award_winner_name,
            "award_value": str(n.award_value) if n.award_value else None,
        }

        # 1. Raw data from DB (keys summary + full dump)
        raw = n.raw_data or {}
        item["raw_data_keys"] = sorted(raw.keys())
        item["raw_data_full"] = raw

        # Extract noticeIds from raw_data
        notice_ids = raw.get("noticeIds") or []
        item["notice_ids_in_raw"] = notice_ids

        # 2. Fetch workspace detail
        if fetch_workspace and workspace_client and n.source_id:
            try:
                ws = workspace_client.get_publication_workspace(n.source_id)
                if ws:
                    item["workspace_detail_keys"] = sorted(ws.keys()) if isinstance(ws, dict) else str(type(ws))
                    item["workspace_detail"] = ws
                else:
                    item["workspace_detail"] = None
                    item["workspace_detail_error"] = "returned None (404/401/403?)"
            except Exception as e:
                item["workspace_detail_error"] = str(e)

        # 3. Fetch notice detail for each noticeId
        if fetch_notice and workspace_client and notice_ids:
            item["notice_details"] = []
            for nid in notice_ids[:3]:  # max 3 per notice
                try:
                    nd = workspace_client.get_notice(nid)
                    if nd:
                        item["notice_details"].append({
                            "notice_id": nid,
                            "keys": sorted(nd.keys()) if isinstance(nd, dict) else str(type(nd)),
                            "detail": nd,
                        })
                    else:
                        item["notice_details"].append({
                            "notice_id": nid,
                            "error": "returned None (404/401/403?)",
                        })
                except Exception as e:
                    item["notice_details"].append({
                        "notice_id": nid,
                        "error": str(e),
                    })

        results.append(item)

    return {
        "notice_sub_type": notice_sub_type,
        "sample_count": len(results),
        "client_available": workspace_client is not None,
        "samples": results,
    }


# ── BOSA CAN award parsing (eForms XML) ─────────────────────────────


@router.get("/bosa-parse-awards-test")
def bosa_parse_awards_test(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Test the eForms XML parser on a few BOSA CAN notices.
    Returns parsed award data WITHOUT updating the DB.
    """
    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Find BOSA CANs (type 29) that have raw_data with versions
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        item: dict[str, Any] = {
            "id": str(row[0]),
            "source_id": row[1],
            "title": row[2],
        }
        raw_data = row[3]
        if not isinstance(raw_data, dict):
            try:
                raw_data = json.loads(raw_data) if raw_data else {}
            except (json.JSONDecodeError, TypeError):
                raw_data = {}

        xml_content = extract_xml_from_raw_data(raw_data)
        if not xml_content:
            item["status"] = "no_xml_found"
            item["versions_count"] = len(raw_data.get("versions", []))
            results.append(item)
            continue

        item["xml_length"] = len(xml_content)
        parsed = parse_award_data(xml_content)
        fields = build_notice_fields(parsed)

        # Convert Decimals to str for JSON serialization
        serializable_parsed = _serialize_parsed(parsed)

        item["status"] = "parsed"
        item["parsed"] = serializable_parsed
        item["db_fields"] = {
            k: str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "Decimal" else v
            for k, v in fields.items()
        }
        results.append(item)

    return {
        "test_count": len(results),
        "parsed_ok": sum(1 for r in results if r.get("status") == "parsed"),
        "no_xml": sum(1 for r in results if r.get("status") == "no_xml_found"),
        "results": results,
    }


@router.post("/bosa-enrich-awards")
def bosa_enrich_awards(
    limit: int = Query(50000, ge=1, le=200000),
    batch_size: int = Query(500, ge=10, le=2000),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Bulk-enrich BOSA CAN (type 29) notices with award data parsed from eForms XML.
    Updates: award_winner_name, award_value, award_date, number_tenders_received, award_criteria_json.
    """
    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Count eligible CANs (type 29 with raw_data, award fields empty)
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '')"
    ))
    total_eligible = count_result.scalar()

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "dry_run": True,
            "message": "Set dry_run=false to execute enrichment",
        }

    # Process in batches — we MUST load raw_data so we use ORM selectively
    enriched = 0
    skipped = 0
    errors = 0
    batches = 0
    offset = 0

    while enriched + skipped + errors < limit:
        rows = db.execute(text(
            "SELECT id, raw_data FROM notices "
            "WHERE source = 'BOSA_EPROC' "
            "  AND notice_sub_type = '29' "
            "  AND raw_data IS NOT NULL "
            "  AND (award_winner_name IS NULL OR award_winner_name = '') "
            "ORDER BY id "
            "LIMIT :batch_size OFFSET :offset"
        ), {"batch_size": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        batch_updates = []
        for row in rows:
            notice_id = row[0]
            raw_data = row[1]

            try:
                if not isinstance(raw_data, dict):
                    raw_data = json.loads(raw_data) if raw_data else {}

                xml_content = extract_xml_from_raw_data(raw_data)
                if not xml_content:
                    # Mark as processed to prevent infinite re-query
                    batch_updates.append((notice_id, {"award_winner_name": "—"}))
                    skipped += 1
                    continue

                parsed = parse_award_data(xml_content)
                fields = build_notice_fields(parsed)

                # Always ensure award_winner_name is set to exit eligibility
                if "award_winner_name" not in fields:
                    fields["award_winner_name"] = "—"

                if not fields:
                    batch_updates.append((notice_id, {"award_winner_name": "—"}))
                    skipped += 1
                    continue

                batch_updates.append((notice_id, fields))

            except Exception as e:
                logger.warning("Award parse error for notice %s: %s", notice_id, e)
                errors += 1

        # Bulk UPDATE via individual statements per notice (fields vary)
        for notice_id, fields in batch_updates:
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
                # Serialize Decimals for JSON storage
                params["acjson"] = json.dumps(
                    fields["award_criteria_json"],
                    default=str,
                )

            if set_clauses:
                set_clauses.append("updated_at = now()")
                sql = f"UPDATE notices SET {', '.join(set_clauses)} WHERE id = :nid"
                db.execute(text(sql), params)
                enriched += 1

        db.commit()
        batches += 1
        offset += batch_size

        logger.info(
            "Award enrichment batch %d: enriched=%d, skipped=%d, errors=%d",
            batches, enriched, skipped, errors,
        )

    return {
        "total_eligible": total_eligible,
        "enriched": enriched,
        "skipped": skipped,
        "errors": errors,
        "batches": batches,
        "dry_run": False,
    }


def _serialize_parsed(parsed: dict) -> dict:
    """Convert Decimal/date values to JSON-safe types."""
    out = {}
    for k, v in parsed.items():
        if v is None:
            out[k] = None
        elif isinstance(v, list):
            out[k] = [
                {
                    kk: str(vv) if hasattr(vv, "__class__") and vv.__class__.__name__ in ("Decimal", "date") else vv
                    for kk, vv in item.items()
                }
                if isinstance(item, dict) else item
                for item in v
            ]
        elif hasattr(v, "__class__") and v.__class__.__name__ in ("Decimal", "date"):
            out[k] = str(v)
        else:
            out[k] = v
    return out


@router.get("/bosa-can-formats")
def bosa_can_formats(
    limit: int = Query(500, ge=10, le=5000),
    db: Session = Depends(get_db),
):
    """
    Diagnose raw_data formats across BOSA CAN (type 29) notices.
    Helps understand why most notices were skipped during award enrichment.
    """
    rows = db.execute(text(
        "SELECT id, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    formats: dict[str, int] = {}
    top_level_keys: dict[str, int] = {}
    samples: dict[str, list] = {}

    for row in rows:
        raw = row[1]
        if not isinstance(raw, dict):
            try:
                raw = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                raw = {}

        # Classify format
        has_versions = "versions" in raw and isinstance(raw.get("versions"), list) and len(raw.get("versions", [])) > 0
        has_xml = False
        if has_versions:
            for v in raw["versions"]:
                if isinstance(v, dict) and isinstance(v.get("notice"), dict):
                    xml = v["notice"].get("xmlContent", "")
                    if isinstance(xml, str) and xml.startswith("<?xml"):
                        has_xml = True
                        break

        has_flat_fields = any(
            k in raw for k in ["publicationType", "publicationWorkspaceId", "dossierStatus", "natures"]
        )

        if has_xml:
            fmt = "versions_with_xml"
        elif has_versions:
            fmt = "versions_no_xml"
        elif has_flat_fields:
            fmt = "flat_enriched"
        elif raw:
            fmt = "other"
        else:
            fmt = "empty"

        formats[fmt] = formats.get(fmt, 0) + 1

        # Track top-level keys
        for k in raw.keys():
            top_level_keys[k] = top_level_keys.get(k, 0) + 1

        # Keep 1 sample per format
        if fmt not in samples:
            samples[fmt] = [{
                "id": str(row[0]),
                "top_keys": sorted(raw.keys())[:20],
                "versions_count": len(raw.get("versions", [])) if has_versions else 0,
            }]

    return {
        "analyzed": len(rows),
        "formats": formats,
        "top_level_keys_frequency": dict(sorted(top_level_keys.items(), key=lambda x: -x[1])[:25]),
        "samples": samples,
    }


@router.get("/bosa-can-flat-peek")
def bosa_can_flat_peek(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Peek at flat_enriched CAN notices: show content of lots, noticeIds, dossier fields.
    Helps decide if award data is already present or needs API fetch.
    """
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data "
        "FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit}).fetchall()

    results = []
    for row in rows:
        raw = row[3]
        if not isinstance(raw, dict):
            try:
                raw = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                raw = {}

        # Skip ones with versions (XML format)
        if "versions" in raw and isinstance(raw.get("versions"), list) and raw["versions"]:
            continue

        item: dict[str, Any] = {
            "id": str(row[0]),
            "source_id": row[1],
            "title": (row[2] or "")[:100],
            "all_keys": sorted(raw.keys()),
            "lots": raw.get("lots"),
            "noticeIds": raw.get("noticeIds"),
            "dossier": raw.get("dossier"),
            "natures": raw.get("natures"),
            "status": raw.get("status"),
            "migrated": raw.get("migrated"),
            "noticeSubType": raw.get("noticeSubType"),
            "organisation_name": raw.get("organisation_name"),
            "organisation": raw.get("organisation"),
        }
        results.append(item)

    return {
        "count": len(results),
        "results": results,
    }


# ── Bulk fetch + enrich via BOSA workspace API ──────────────────────


@router.post(
    "/bosa-enrich-awards-via-api",
    summary="Bulk-enrich flat BOSA CANs via workspace API",
    description=(
        "For each CAN (type 29) without award data and without XML in raw_data:\n"
        "1. GET /publication-workspaces/{source_id} → workspace detail with eForms XML\n"
        "2. Parse XML for award data (winner, value, date, nb tenders)\n"
        "3. Update notice fields + replace raw_data with full workspace response\n\n"
        "Rate-limited with configurable delay between API calls.\n"
        "Use dry_run=true first to see count + estimated time."
    ),
)
def bosa_enrich_awards_via_api(
    limit: int = Query(100, ge=1, le=50000),
    batch_size: int = Query(50, ge=5, le=500),
    api_delay_ms: int = Query(300, ge=50, le=5000),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Bulk-enrich flat BOSA CANs by fetching workspace detail via API.

    For each CAN (type 29) without award data and without XML in raw_data:
    1. GET /publication-workspaces/{source_id} → workspace detail with XML
    2. Parse eForms XML for award data
    3. Update notice fields + replace raw_data with full workspace response

    Rate-limited with configurable delay between API calls.
    """
    import time

    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Count eligible: CAN type 29, no award data
    count_result = db.execute(text(
        "SELECT COUNT(*) FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '')"
    ))
    total_eligible = count_result.scalar()

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "limit": limit,
            "batch_size": batch_size,
            "api_delay_ms": api_delay_ms,
            "dry_run": True,
            "message": "Set dry_run=false to execute. This will make API calls to BOSA.",
            "estimated_time_minutes": round(
                min(total_eligible, limit) * api_delay_ms / 60000, 1
            ),
        }

    # Initialize BOSA API client
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, provider = _get_client()
        if not isinstance(client, OfficialEProcurementClient):
            return {"error": f"BOSA client is not official ({provider}), cannot fetch workspace details"}
    except Exception as e:
        return {"error": f"Failed to initialize BOSA client: {e}"}

    enriched = 0
    skipped_no_xml = 0
    skipped_no_fields = 0
    api_errors = 0
    parse_errors = 0
    already_has_xml = 0
    batches_done = 0
    offset = 0
    delay_sec = api_delay_ms / 1000.0

    while (enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml) < limit:
        # Fetch batch of flat CANs
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
            if (enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml) >= limit:
                break

            notice_id = row[0]
            source_id = row[1]
            raw_data = row[2]

            try:
                if not isinstance(raw_data, dict):
                    raw_data = json.loads(raw_data) if raw_data else {}

                # Check if raw_data already has XML (skip API call)
                existing_xml = extract_xml_from_raw_data(raw_data)
                if existing_xml:
                    # Already has XML — parse directly (shouldn't happen often since
                    # bosa_enrich_awards already handled these, but just in case)
                    parsed = parse_award_data(existing_xml)
                    fields = build_notice_fields(parsed)
                    if fields:
                        _update_notice_fields(db, notice_id, fields)
                        enriched += 1
                    else:
                        skipped_no_fields += 1
                    already_has_xml += 1
                    continue

                # Fetch workspace detail via API
                if not source_id:
                    skipped_no_xml += 1
                    continue

                time.sleep(delay_sec)
                workspace_data = client.get_publication_workspace(source_id)

                if not workspace_data:
                    api_errors += 1
                    continue

                # Extract XML from workspace response
                xml_content = extract_xml_from_raw_data(workspace_data)
                if not xml_content:
                    skipped_no_xml += 1
                    continue

                # Parse award data
                parsed = parse_award_data(xml_content)
                fields = build_notice_fields(parsed)

                if not fields:
                    skipped_no_fields += 1
                    continue

                # Update notice: award fields + replace raw_data with full workspace
                _update_notice_fields(db, notice_id, fields)

                # Also update raw_data with the workspace response (has XML for future use)
                db.execute(
                    text("UPDATE notices SET raw_data = :rd WHERE id = :nid"),
                    {
                        "rd": json.dumps(workspace_data, default=str),
                        "nid": notice_id,
                    },
                )
                enriched += 1

            except Exception as e:
                logger.warning(
                    "Award API enrichment error for notice %s (source=%s): %s",
                    notice_id, source_id, e,
                )
                parse_errors += 1

        db.commit()
        batches_done += 1
        offset += batch_size

        processed = enriched + skipped_no_xml + skipped_no_fields + api_errors + parse_errors + already_has_xml
        logger.info(
            "Award API enrichment batch %d: enriched=%d, api_errors=%d, "
            "skipped_no_xml=%d, skipped_no_fields=%d, parse_errors=%d, "
            "already_has_xml=%d (total processed=%d/%d)",
            batches_done, enriched, api_errors,
            skipped_no_xml, skipped_no_fields, parse_errors,
            already_has_xml, processed, total_eligible,
        )

    return {
        "total_eligible": total_eligible,
        "enriched": enriched,
        "skipped_no_xml": skipped_no_xml,
        "skipped_no_fields": skipped_no_fields,
        "api_errors": api_errors,
        "parse_errors": parse_errors,
        "already_has_xml": already_has_xml,
        "batches": batches_done,
        "dry_run": False,
    }


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


@router.get(
    "/bosa-enrich-debug",
    summary="Debug: step-by-step workspace fetch + parse for a few CANs",
    description=(
        "Fetches workspace detail + parses XML for up to 20 flat CANs.\n"
        "Shows each step: existing XML check → API fetch → XML extract → parse → fields.\n"
        "Use this to diagnose enrichment failures before running bulk."
    ),
)
def bosa_enrich_debug(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Debug endpoint: fetch workspace + parse for a few CANs and show
    exactly what happens at each step (errors, XML presence, parsed data).
    """
    import time
    import traceback

    from app.services.bosa_award_parser import (
        extract_xml_from_raw_data,
        parse_award_data,
        build_notice_fields,
    )

    # Init client
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, provider = _get_client()
        if not isinstance(client, OfficialEProcurementClient):
            return {"error": f"Not official client: {provider}"}
    except Exception as e:
        return {"error": str(e)}

    # Get flat CANs (no XML in raw_data, no award data)
    rows = db.execute(text(
        "SELECT id, source_id, title, raw_data FROM notices "
        "WHERE source = 'BOSA_EPROC' "
        "  AND notice_sub_type = '29' "
        "  AND raw_data IS NOT NULL "
        "  AND (award_winner_name IS NULL OR award_winner_name = '') "
        "ORDER BY publication_date DESC "
        "LIMIT :limit"
    ), {"limit": limit * 3}).fetchall()  # fetch more to skip XML ones

    results = []
    for row in rows:
        if len(results) >= limit:
            break

        notice_id = row[0]
        source_id = row[1]
        title = (row[2] or "")[:80]
        raw_data = row[3]

        item: dict[str, Any] = {
            "id": str(notice_id),
            "source_id": source_id,
            "title": title,
            "steps": {},
        }

        try:
            if not isinstance(raw_data, dict):
                raw_data = json.loads(raw_data) if raw_data else {}

            # Step 1: Check existing XML
            existing_xml = extract_xml_from_raw_data(raw_data)
            if existing_xml:
                item["steps"]["1_existing_xml"] = "FOUND (skipping API)"
                continue  # skip — we want flat ones

            item["steps"]["1_existing_xml"] = "NOT_FOUND (will fetch API)"

            # Step 2: Fetch workspace
            time.sleep(0.3)
            workspace = client.get_publication_workspace(source_id)
            if not workspace:
                item["steps"]["2_api_fetch"] = "FAILED (None returned)"
                results.append(item)
                continue

            ws_keys = sorted(workspace.keys()) if isinstance(workspace, dict) else str(type(workspace))
            item["steps"]["2_api_fetch"] = f"OK — keys: {ws_keys}"

            # Step 3: Extract XML from workspace
            xml_content = extract_xml_from_raw_data(workspace)
            if not xml_content:
                # Check why: does it have versions?
                versions = workspace.get("versions", [])
                version_info = []
                for v in versions:
                    if isinstance(v, dict):
                        notice = v.get("notice")
                        if notice is None:
                            version_info.append("notice=None")
                        elif isinstance(notice, dict):
                            has_xml = bool(notice.get("xmlContent"))
                            version_info.append(f"notice=dict(xmlContent={has_xml})")
                        else:
                            version_info.append(f"notice=type:{type(notice).__name__}")
                    else:
                        version_info.append(f"version=type:{type(v).__name__}")

                item["steps"]["3_extract_xml"] = f"NO XML — {len(versions)} versions: {version_info}"
                results.append(item)
                continue

            item["steps"]["3_extract_xml"] = f"OK — {len(xml_content)} chars"

            # Step 4: Parse award data
            parsed = parse_award_data(xml_content)
            item["steps"]["4_parse"] = {
                "total_amount": str(parsed.get("total_amount")) if parsed.get("total_amount") else None,
                "winners_count": len(parsed.get("winners", [])),
                "tenders_received": parsed.get("tenders_received"),
                "award_date": str(parsed.get("award_date")) if parsed.get("award_date") else None,
            }

            # Step 5: Build fields
            fields = build_notice_fields(parsed)
            item["steps"]["5_fields"] = fields if fields else "EMPTY (no fields generated)"

        except Exception as e:
            item["steps"]["ERROR"] = f"{type(e).__name__}: {e}"
            item["steps"]["traceback"] = traceback.format_exc()[-500:]

        results.append(item)

    return {"count": len(results), "results": results}


