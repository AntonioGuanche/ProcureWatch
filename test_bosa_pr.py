#!/usr/bin/env python3
"""Test BOSA PR (production) credentials — standalone, no project deps needed.

Usage:
  python test_bosa_pr.py
  
  # Or with explicit values:
  python test_bosa_pr.py --client-id YOUR_ID --client-secret YOUR_SECRET

Reads from .env if present (EPROCUREMENT_PR_CLIENT_ID / EPROCUREMENT_PR_CLIENT_SECRET).
"""
import argparse
import os
import sys
import time

try:
    import requests
except ImportError:
    print("❌ 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# --- PR endpoints ---
PR_TOKEN_URL = "https://public.pr.fedservices.be/api/oauth2/token"
PR_SEA_BASE = "https://public.pr.fedservices.be/api/eProcurementSea/v1"
PR_LOC_BASE = "https://public.pr.fedservices.be/api/eProcurementLoc/v1"
PR_DOS_BASE = "https://public.pr.fedservices.be/api/eProcurementDos/v1"

# --- INT endpoints (for comparison) ---
INT_TOKEN_URL = "https://public.int.fedservices.be/api/oauth2/token"
INT_SEA_BASE = "https://public.int.fedservices.be/api/eProcurementSea/v1"


def load_env():
    """Try to load .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_token(token_url: str, client_id: str, client_secret: str) -> dict:
    """Request OAuth2 token via client_credentials."""
    print(f"\n🔑 Requesting token from: {token_url}")
    print(f"   Client ID: {client_id[:8]}...{client_id[-4:]}" if len(client_id) > 12 else f"   Client ID: {client_id}")
    
    start = time.time()
    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        elapsed = time.time() - start
        
        print(f"   Status: {resp.status_code} ({elapsed:.1f}s)")
        
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token", "")
            expires = data.get("expires_in", "?")
            print(f"   ✅ Token obtained! Expires in {expires}s")
            print(f"   Token preview: {token[:20]}...{token[-10:]}" if len(token) > 30 else f"   Token: {token}")
            return {"ok": True, "token": token, "data": data}
        else:
            print(f"   ❌ FAILED: {resp.status_code}")
            print(f"   Response: {resp.text[:500]}")
            return {"ok": False, "status": resp.status_code, "body": resp.text}
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return {"ok": False, "error": str(e)}


def test_search(base_url: str, token: str, label: str) -> bool:
    """Test search endpoint with token."""
    import uuid
    url = f"{base_url}/search/publications"
    print(f"\n🔍 Testing {label} search: {url}")
    
    try:
        resp = requests.get(
            url,
            params={"searchTerm": "test", "page": 1, "pageSize": 3},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "BelGov-Trace-Id": str(uuid.uuid4()),
                "Accept-Language": "fr",
            },
            timeout=15,
        )
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            total = data.get("totalCount", data.get("total", "?"))
            items = data.get("publications", data.get("items", []))
            print(f"   ✅ OK — {total} total results, {len(items)} returned")
            if items and isinstance(items, list) and len(items) > 0:
                first = items[0]
                title = first.get("title") or (first.get("dossier", {}) or {}).get("titles", [{}])
                ws_id = first.get("publicationWorkspaceId") or first.get("id")
                print(f"   First result ID: {ws_id}")
            return True
        elif resp.status_code == 401:
            print(f"   ❌ 401 Unauthorized — token not accepted by this environment")
            print(f"   Response: {resp.text[:300]}")
            return False
        elif resp.status_code == 403:
            print(f"   ❌ 403 Forbidden — credentials don't have access to this API")
            print(f"   Response: {resp.text[:300]}")
            return False
        else:
            print(f"   ⚠️  {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False


def test_cpv(base_url: str, token: str, label: str) -> bool:
    """Test LOC CPV endpoint."""
    import uuid
    loc_url = base_url.replace("eProcurementSea", "eProcurementLoc")
    url = f"{loc_url}/cpvs/45000000"
    print(f"\n📋 Testing {label} CPV lookup: {url}")
    
    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "BelGov-Trace-Id": str(uuid.uuid4()),
            },
            timeout=15,
        )
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ OK — CPV data: {str(data)[:200]}")
            return True
        elif resp.status_code == 204:
            print(f"   ⚠️  204 No Content (known issue on some CPV codes)")
            return True  # Not a credential issue
        else:
            print(f"   Response: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test BOSA PR credentials")
    parser.add_argument("--client-id", help="PR Client ID (or set EPROCUREMENT_PR_CLIENT_ID)")
    parser.add_argument("--client-secret", help="PR Client Secret (or set EPROCUREMENT_PR_CLIENT_SECRET)")
    parser.add_argument("--also-int", action="store_true", help="Also test INT credentials for comparison")
    args = parser.parse_args()

    load_env()

    pr_id = args.client_id or os.environ.get("EPROCUREMENT_PR_CLIENT_ID", "")
    pr_secret = args.client_secret or os.environ.get("EPROCUREMENT_PR_CLIENT_SECRET", "")

    if not pr_id or not pr_secret:
        print("❌ No PR credentials found.")
        print("   Set EPROCUREMENT_PR_CLIENT_ID and EPROCUREMENT_PR_CLIENT_SECRET in .env")
        print("   Or pass --client-id and --client-secret")
        sys.exit(1)

    print("=" * 60)
    print("🇧🇪 BOSA eProcurement — PR (Production) Credential Test")
    print("=" * 60)

    # Step 1: Get PR token
    pr_token_result = get_token(PR_TOKEN_URL, pr_id, pr_secret)
    
    if not pr_token_result["ok"]:
        print("\n" + "=" * 60)
        print("❌ RESULT: PR token request FAILED")
        print("   → Credentials are invalid or not authorized for PR environment")
        print("   → Check with BOSA if your credentials are activated for production")
        
        # Try same credentials against INT to diagnose
        print("\n🔄 Testing same credentials against INT (diagnostic)...")
        int_result = get_token(INT_TOKEN_URL, pr_id, pr_secret)
        if int_result["ok"]:
            print("   ⚠️  Same credentials WORK on INT but NOT on PR")
            print("   → Your credentials are INT-only. Contact BOSA for PR access.")
        else:
            print("   ❌ Credentials don't work on INT either — they may be expired/revoked")
        sys.exit(1)

    pr_token = pr_token_result["token"]

    # Step 2: Test PR Search
    search_ok = test_search(PR_SEA_BASE, pr_token, "PR")

    # Step 3: Test PR CPV
    cpv_ok = test_cpv(PR_SEA_BASE, pr_token, "PR")

    # Optional: compare with INT
    if args.also_int:
        int_id = os.environ.get("EPROCUREMENT_INT_CLIENT_ID", "")
        int_secret = os.environ.get("EPROCUREMENT_INT_CLIENT_SECRET", "")
        if int_id and int_secret:
            print("\n" + "-" * 40)
            print("📊 Comparison: INT environment")
            int_token_result = get_token(INT_TOKEN_URL, int_id, int_secret)
            if int_token_result["ok"]:
                test_search(INT_SEA_BASE, int_token_result["token"], "INT")

    # Summary
    print("\n" + "=" * 60)
    print("📊 RÉSULTAT")
    print("=" * 60)
    
    if pr_token_result["ok"] and search_ok:
        print("✅ Credentials PR fonctionnelles !")
        print("   → Tu peux basculer EPROCUREMENT_ENV=PR dans Railway")
        print("   → Les imports utiliseront les données de production")
    elif pr_token_result["ok"] and not search_ok:
        print("⚠️  Token PR obtenu mais recherche échoue (401/403)")
        print("   → Le token est valide mais n'a peut-être pas les bons scopes")
        print("   → Vérifie avec BOSA que le scope eProcurementSea est activé")
    else:
        print("❌ Credentials PR non fonctionnelles")


if __name__ == "__main__":
    main()
