#!/usr/bin/env python3
"""Check e-Procurement configuration (resolved values, no secrets printed)."""
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
from app.connectors.bosa.openapi_discovery import cache_path


def mask_secret(value: str | None, show_length: bool = True) -> str:
    """
    Mask secret value, showing only first 10 chars and length if requested.
    Detects placeholders and marks them as such.
    """
    if not value:
        return "(empty)"
    
    # Check if it's a placeholder using the same logic as config
    from app.core.config import Settings
    if Settings.is_placeholder(value):
        return f"{value} (placeholder)"
    
    # Mask real values: show first 10 chars, then "..."
    if len(value) <= 10:
        return "***" + (f" (length={len(value)})" if show_length else "")
    
    masked = value[:10] + "..."
    if show_length:
        return f"{masked} (length={len(value)})"
    return masked


def main() -> int:
    """Print resolved e-Procurement configuration."""
    print("=== e-Procurement Configuration Check ===\n")
    
    print(f"Mode: {settings.eproc_mode}")
    print(f"Environment: {settings._resolve_eproc_env_name()}")
    print()
    
    # Resolve canonical config
    try:
        config = settings.resolve_eproc_official_config()
        print("Resolved configuration:")
        print(f"  Token URL: {config['token_url']}")
        print(f"  Client ID: {mask_secret(config['client_id'])}")
        print(f"  Client Secret: {mask_secret(config['client_secret'])}")
        print(f"  Search Base URL: {config['search_base_url']}")
        print(f"  Location Base URL: {config['loc_base_url']}")
        print()
        
        # Validation
        try:
            settings.validate_eproc_official_config()
            print("[OK] Configuration is valid")
        except ValueError as e:
            print(f"[ERROR] Configuration error: {e}")
            return 1
    except Exception as e:
        print(f"[ERROR] Error resolving configuration: {e}")
        return 1
    
    print()
    
    # Check endpoints cache
    cache_file = cache_path()
    print(f"Endpoints cache: {cache_file}")
    print(f"  Exists: {cache_file.exists()}")
    if cache_file.exists():
        import json
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            confirmed = data.get("confirmed", False)
            print(f"  Confirmed: {confirmed}")
            print(f"  Updated at: {data.get('updated_at', 'unknown')}")
            if confirmed:
                print("  [OK] Endpoints are confirmed - API calls enabled")
            else:
                print("  [WARN] Endpoints NOT confirmed - run discovery with --confirm")
        except Exception as e:
            print(f"  Error reading cache: {e}")
    else:
        print("  [WARN] Cache not found - run discovery first")
    
    print()
    
    # Check env var confirmation
    import os
    env_confirmed = os.environ.get("EPROCUREMENT_ENDPOINT_CONFIRMED", "").strip()
    if env_confirmed:
        print(f"EPROCUREMENT_ENDPOINT_CONFIRMED={env_confirmed} (env var)")
    else:
        print("EPROCUREMENT_ENDPOINT_CONFIRMED not set (using cache)")
    
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
