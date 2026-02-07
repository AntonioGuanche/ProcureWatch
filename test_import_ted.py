"""Test TED import into DB. Uses sync search_ted_notices; asyncio only for import."""
import asyncio

from connectors.ted.client import search_ted_notices

from app.db.session import SessionLocal
from app.models.notice import NoticeSource, ProcurementNotice
from app.services.notice_service import NoticeService


async def test_import_ted():
    print("=== Test Import TED → DB ===")

    # 1. DB session and service
    db = SessionLocal()
    service = NoticeService(db)

    # 2. Search via TED API (SYNC - do not use asyncio.run for this)
    result = search_ted_notices(term="construction", page_size=5)
    # Use top-level "notices" list (per TED response structure)
    notices_list = result.get("notices") or result.get("json") or {}
    if isinstance(notices_list, dict):
        notices_list = notices_list.get("notices") or []
    if not isinstance(notices_list, list):
        notices_list = []

    metadata = result.get("metadata") or {}
    json_payload = result.get("json") or {}
    total = (
        metadata.get("totalCount")
        or (json_payload.get("totalNoticeCount") if isinstance(json_payload, dict) else None)
        or (json_payload.get("totalCount") if isinstance(json_payload, dict) else None)
        or len(notices_list)
    )

    print(f"✅ Search: {total} total, {len(notices_list)} fetched")

    # 3. Import into DB (async method)
    stats = await service.import_from_ted_search(
        notices_list,
        fetch_details=False,
    )

    print(f"✅ Import: {stats}")

    # 4. Verification: count TED notices only
    ted_count = (
        db.query(ProcurementNotice)
        .filter(ProcurementNotice.source == NoticeSource.TED_EU.value)
        .count()
    )
    print(f"✅ Total TED notices in DB: {ted_count}")

    # Show imported notices (same format as test_import.py)
    latest = (
        db.query(ProcurementNotice)
        .filter(ProcurementNotice.source == NoticeSource.TED_EU.value)
        .order_by(ProcurementNotice.created_at.desc())
        .limit(5)
        .all()
    )
    for notice in latest:
        print(f"  - {notice.source_id}: {notice.cpv_main_code} | {notice.organisation_names}")

    db.close()


if __name__ == "__main__":
    asyncio.run(test_import_ted())
