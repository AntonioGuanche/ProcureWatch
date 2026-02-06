"""Smoke test for BOSA e-Procurement OAuth2 (Client Credentials) configuration."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from app.core.config import settings


def main():
    """Test BOSA OAuth2 token request."""
    env = settings.eprocurement_env.upper()
    token_url = settings.bosa_token_url
    client_id = settings.bosa_client_id
    client_secret = settings.bosa_client_secret

    print(f"Environment: {env}")
    print(f"Token URL: {token_url}")

    if not client_id or not client_secret:
        print("ERROR: Client ID or Client Secret not configured")
        print(f"  Set EPROCUREMENT_{env}_CLIENT_ID and EPROCUREMENT_{env}_CLIENT_SECRET in .env")
        sys.exit(1)

    try:
        response = requests.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in")

        if not access_token:
            print("ERROR: Token response did not contain access_token")
            sys.exit(1)

        print("Success: Token obtained")
        print(f"Expires in: {expires_in} seconds")
        # Do NOT print the token value or secrets

    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code}")
        print(f"Response: {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
