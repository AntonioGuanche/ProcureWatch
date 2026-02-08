# Créer script test simple
@"
import asyncio
import traceback
from app.connectors.eprocurement import EprocurementConnector

async def test():
    conn = EprocurementConnector()
    
    try:
        print("1. Testing token...")
        token = await conn._get_access_token()
        print(f"   Token OK: {len(token) > 0 if token else False}")
        print(f"   Token preview: {token[:50] if token else 'NONE'}...")
        
        print("\n2. Testing search...")
        results = await conn.search_publications(
            query="*",
            page_size=5,
            date_from="2026-02-01",
            date_to="2026-02-08"
        )
        
        print(f"   Results: {len(results.get('items', []))} items")
        print(f"   Total: {results.get('totalElements', 0)}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nFull traceback:")
        traceback.print_exc()

asyncio.run(test())
"@ | Out-File -FilePath test_bosa.py -Encoding utf8

