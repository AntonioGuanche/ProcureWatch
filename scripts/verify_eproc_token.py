#!/usr/bin/env python3
"""Verify e-Procurement OAuth token retrieval (no secrets printed)."""
import sys
from pathlib import Path

# Determine repo root and load .env explicitly before any imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env explicitly for standalone script execution
_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        # python-dotenv not installed - that's OK, pydantic-settings will load it
        pass

from app.utils.env import load_env_if_present
load_env_if_present()

from app.core.config import settings
from app.connectors.bosa.exceptions import (
    EProcurementCredentialsError,
    EProcurementEndpointNotConfiguredError,
)
from app.connectors.bosa.official_client import OfficialEProcurementClient


def main() -> int:
    """Attempt token retrieval and print status."""
    print("=== e-Procurement Token Verification ===\n")
    
    if settings.eproc_mode.lower() not in ("official", "auto"):
        print(f"EPROC_MODE={settings.eproc_mode} - token verification only works in official/auto mode")
        return 1
    
    try:
        config = settings.resolve_eproc_official_config()
        print(f"Environment: {config['env_name']}")
        print(f"Token URL: {config['token_url']}")
        print()
        
        # Validate config first
        settings.validate_eproc_official_config()
        print("[OK] Configuration valid")
        print()
        
        # Create client
        client = OfficialEProcurementClient(
            token_url=config["token_url"],
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            search_base_url=config["search_base_url"],
            loc_base_url=config["loc_base_url"],
            timeout_seconds=settings.eproc_timeout_seconds,
        )
        
        # Attempt token retrieval
        print("Attempting token retrieval...")
        try:
            token = client.get_access_token()
            print("[OK] Token retrieved successfully")
            print(f"  Token length: {len(token)} characters")
            print(f"  Token preview: {token[:20]}...")
            print(f"  Expires in: {int(client._token_expires_at - __import__('time').time())} seconds")
            return 0
        except EProcurementCredentialsError as e:
            print(f"[ERROR] Credentials error: {e}")
            return 1
        except EProcurementEndpointNotConfiguredError as e:
            print(f"[ERROR] Endpoint configuration error: {e}")
            print("\nHint: Run: python scripts/discover_eprocurement_endpoints.py --confirm")
            return 1
        except Exception as e:
            print(f"[ERROR] Token retrieval failed: {e}")
            return 1
            
    except ValueError as e:
        print(f"[ERROR] Configuration error: {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
