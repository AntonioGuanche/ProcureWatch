import asyncio

from connectors.eprocurement.client import search_publications

from app.db.session import SessionLocal
from app.services.notice_service import NoticeService

async def test_import():
    print("=== Test Import BOSA → DB ===")

    # 1. DB session and service
    db = SessionLocal()
    service = NoticeService(db)

    # 2. Search via BOSA API (uses configured client)
    result = search_publications(term="construction", page=1, page_size=5)
    payload = result.get("json") or {}
    items = None
    if isinstance(payload, dict):
        for key in ("publications", "items", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
    if not items:
        items = []
    metadata = result.get("metadata") or {}
    total = metadata.get("totalCount", len(items))

    print(f"✅ Search: {total} total, {len(items)} fetched")

    # 3. Import into DB
    stats = await service.import_from_eproc_search(
        items,
        fetch_details=True,
    )
    
    print(f"✅ Import: {stats}")
    
    # 4. Vérification DB
    from app.models.notice import ProcurementNotice
    count = db.query(ProcurementNotice).count()
    print(f"✅ Total notices in DB: {count}")
    
    # Afficher les 3 dernières
    latest = db.query(ProcurementNotice).order_by(ProcurementNotice.created_at.desc()).limit(3).all()
    for notice in latest:
        print(f"  - {notice.source_id}: {notice.cpv_main_code} | {notice.organisation_names}")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(test_import())