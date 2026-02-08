#!/usr/bin/env python3
"""Show e-Procurement configuration diagnostics (endpoints cache, env vars)."""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present
from app.utils.env import load_env_if_present
load_env_if_present()


def main() -> int:
    """Print diagnostics about e-Procurement configuration."""
    print("=== e-Procurement Configuration Diagnostics ===\n")
    
    # Check endpoints cache
    try:
        from app.connectors.bosa.openapi_discovery import cache_path
        cache_file = cache_path()
        print(f"Endpoints cache file: {cache_file}")
        print(f"  Exists: {cache_file.exists()}")
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                confirmed = data.get("confirmed", False)
                print(f"  Confirmed: {confirmed}")
                print(f"  Updated at: {data.get('updated_at', 'unknown')}")
                if data.get("search_publications"):
                    sp = data["search_publications"]
                    print(f"  Search endpoint: {sp.get('method', '?')} {sp.get('path', '?')}")
                else:
                    print("  Search endpoint: (not found)")
            except Exception as e:
                print(f"  Error reading cache: {e}")
        else:
            print("  Status: Not found - run discovery first")
    except Exception as e:
        print(f"Error checking endpoints cache: {e}")
    
    print()
    
    # Check expected environment variables (names only, not values)
    expected_vars = [
        "EPROC_MODE",
        "EPROC_CLIENT_ID",
        "EPROC_CLIENT_SECRET",
        "EPROC_SEARCH_BASE_URL",
        "EPROCUREMENT_ENV",
        "EPROCUREMENT_INT_CLIENT_ID",
        "EPROCUREMENT_INT_CLIENT_SECRET",
        "EPROCUREMENT_PR_CLIENT_ID",
        "EPROCUREMENT_PR_CLIENT_SECRET",
        "EPROCUREMENT_ENDPOINT_CONFIRMED",
    ]
    
    print("Environment variables:")
    for var_name in expected_vars:
        value = os.environ.get(var_name)
        if value is not None:
            # Show SET but mask value (show first 4 chars + ... if long)
            if len(value) > 8:
                masked = value[:4] + "..." + value[-2:]
            else:
                masked = "***" if len(value) > 0 else "(empty)"
            print(f"  {var_name}: SET ({masked})")
        else:
            print(f"  {var_name}: MISSING")
    
    print()
    print("Note: Values are masked for security. Check .env file for actual values.")
    return 0


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
