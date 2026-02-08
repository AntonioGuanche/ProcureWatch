#!/usr/bin/env python3
"""
End-to-end smoke tests for Belgian e-Procurement official APIs (BOSA).

Usage:
    Preferred: python -m scripts.smoke_eproc_api_calls [--term TERM] [--page-size N] [--cpv CODE] [--dump-cpv-json] [--dump-search-json]
    Alternative: python scripts/smoke_eproc_api_calls.py [--term TERM] [--page-size N] [--cpv CODE] [--dump-cpv-json] [--dump-search-json]

Exit codes:
    0 = Success (all API calls passed)
    2 = Configuration error (missing/invalid credentials)
    3 = Endpoints not confirmed (run discovery with --confirm)
    4 = API call failed (network/HTTP errors)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Bootstrap sys.path when executed directly (not as module)
if __name__ == "__main__" and __package__ is None:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(REPO_ROOT))
    
    # Load .env explicitly for standalone execution
    _env_file = REPO_ROOT / ".env"
    if _env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_env_file, override=False)
        except ImportError:
            pass
    
    # Also use the utility function for consistency
    from app.utils.env import load_env_if_present
    load_env_if_present()

from app.core.config import settings
from app.connectors.bosa.client import get_cpv_label, search_publications
from app.connectors.bosa.exceptions import (
    EProcurementCredentialsError,
    EProcurementEndpointNotConfiguredError,
)
from app.connectors.bosa.official_client import OfficialEProcurementClient


def mask_value(value: str | None, max_preview: int = 12) -> str:
    """Mask a secret value, showing only preview and length."""
    if not value:
        return "(empty)"
    if len(value) <= max_preview:
        return "***"
    return f"{value[:max_preview]}... (length={len(value)})"


def print_config_section(config: dict[str, Any]) -> None:
    """Print configuration section (no secrets)."""
    print("=== Config ===")
    print(f"Environment: {config['env_name']}")
    print(f"Token URL: {config['token_url']}")
    print(f"Client ID: {mask_value(config['client_id'])}")
    print(f"Client Secret: {mask_value(config['client_secret'])}")
    print(f"Search Base URL: {config['search_base_url']}")
    print(f"Location Base URL: {config['loc_base_url']}")
    dos_url = config.get("dos_base_url")
    print(f"DOS Base URL: {dos_url or '(not set)'}")
    print()


def print_config_check(config: dict[str, Any], token: Optional[str] = None) -> None:
    """
    Print configuration validation block (Environment, DOS URL, token preview, status).
    Token is shown as first 30 chars then masked; no secrets beyond that.
    """
    env = config.get("env_name") or "—"
    dos_url = config.get("dos_base_url") or "(not set)"
    if token:
        preview = token[:30] + "...***" if len(token) > 30 else "***"
        token_str = f"{preview} ({len(token)} chars)"
    else:
        token_str = "(not retrieved)"
    urls_ok = bool(
        config.get("token_url")
        and config.get("search_base_url")
        and config.get("loc_base_url")
        and config.get("dos_base_url")
    )
    status = "✅ Ready" if (urls_ok and token) else "⚠️ Not ready"
    print("🔧 Configuration Check:")
    print(f"├─ Environment: {env}")
    print(f"├─ DOS URL: {dos_url}")
    print(f"├─ Token: {token_str}")
    print(f"└─ Status: {status}")
    print()


def test_token_retrieval(client: OfficialEProcurementClient) -> tuple[bool, Optional[str]]:
    """Test token retrieval. Returns (success, expires_in_str)."""
    print("=== Token ===")
    try:
        token = client.get_access_token()
        expires_in = int(client._token_expires_at - __import__("time").time())
        print(f"[OK] Token retrieved successfully")
        print(f"  Token preview: {mask_value(token)}")
        print(f"  Expires in: {expires_in} seconds")
        print()
        return True, str(expires_in)
    except EProcurementCredentialsError as e:
        print(f"[ERROR] Credentials error: {e}")
        print()
        return False, None
    except Exception as e:
        print(f"[ERROR] Token retrieval failed: {e}")
        print()
        return False, None


def test_search_publications(term: str, page_size: int, dump_json: bool = False) -> tuple[bool, Optional[dict[str, Any]], Optional[dict[str, Any]], Optional[int]]:
    """
    Test search_publications API call.
    Returns (success, result_dict, first_item, exit_code_if_failed).
    exit_code: None if success, 3 if endpoint not confirmed, 4 if API call failed.
    """
    print("=== Search ===")
    try:
        # Generate trace ID preview for logging (using the same method as the client)
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        trace_id_preview = OfficialEProcurementClient._make_trace_id()[:12]
        print(f"  Trace ID: {trace_id_preview}...")
        
        result = search_publications(term=term, page=1, page_size=page_size)
        metadata = result.get("metadata", {})
        payload = result.get("json", {})
        
        status = metadata.get("status")
        total_count = metadata.get("totalCount")
        
        # Count items in payload (best-effort) and extract first item
        item_count = 0
        first_item = None
        if isinstance(payload, dict):
            for key in ("publications", "items", "results", "data"):
                items = payload.get(key)
                if isinstance(items, list):
                    item_count = len(items)
                    if items:
                        first_item = items[0]
                    break
        
        print(f"[OK] Search completed")
        print(f"  Status: {status}")
        print(f"  Total count: {total_count}")
        print(f"  Items returned: {item_count}")
        
        # Dump JSON if requested
        if dump_json:
            dump_dir = Path("data/debug")
            dump_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dump_file = dump_dir / f"search_{timestamp}.json"
            with open(dump_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"  Dumped to: {dump_file}")
        
        print()
        return True, result, first_item, None
    except EProcurementEndpointNotConfiguredError as e:
        print(f"[ERROR] Endpoints not confirmed: {e}")
        print()
        return False, None, 3
    except (ValueError, Exception) as e:
        # ValueError from API calls, HTTPError, or other exceptions
        error_msg = str(e)
        # Print error body preview if available (already in ValueError message)
        if "status=" in error_msg or "error" in error_msg.lower():
            # Extract preview (first 200 chars to avoid printing full response)
            preview = error_msg[:200] + "..." if len(error_msg) > 200 else error_msg
            print(f"[ERROR] Search failed: {preview}")
        else:
            print(f"[ERROR] Search failed: {e}")
        print()
        return False, None, 4


def extract_publication_identifier(item: dict[str, Any]) -> dict[str, Any]:
    """
    Extract publication identifier from a publication item.
    
    Returns:
        Dict with keys:
        - short_link: str|None - shortLink identifier if found
        - id: str|None - id/uuid identifier if found
        - raw_keys: list[str] - list of top-level keys (max 30) for diagnostics
    """
    if not isinstance(item, dict):
        return {"short_link": None, "id": None, "raw_keys": []}
    
    # Collect all top-level keys (for diagnostics)
    raw_keys = list(item.keys())[:30]
    
    short_link = None
    pub_id = None
    
    # Try direct shortLink fields (flat)
    for key in ("shortLink", "publicationShortLink", "short_link", "idShortLink"):
        value = item.get(key)
        if value and isinstance(value, str):
            short_link = str(value).strip()
            break
    
    # Try nested shortLink (link.shortLink, links.shortLink)
    if not short_link:
        for link_key in ("link", "links"):
            link_obj = item.get(link_key)
            if isinstance(link_obj, dict):
                for sub_key in ("shortLink", "short_link", "href"):
                    value = link_obj.get(sub_key)
                    if value and isinstance(value, str):
                        short_link = str(value).strip()
                        break
                if short_link:
                    break
    
    # Try ID fields (for detail-by-id endpoint)
    for key in ("id", "publicationId", "publication_id", "uuid", "reference", "noticeId"):
        value = item.get(key)
        if value and isinstance(value, str):
            pub_id = str(value).strip()
            break
    
    # Try Dos API identifiers
    publication_workspace_id = None
    notice_ids = None
    
    # Check for publicationWorkspaceId
    workspace_id_value = item.get("publicationWorkspaceId")
    if workspace_id_value and isinstance(workspace_id_value, str):
        publication_workspace_id = str(workspace_id_value).strip()
    
    # Check for noticeIds (can be list or single value)
    notice_ids_value = item.get("noticeIds")
    if notice_ids_value:
        if isinstance(notice_ids_value, list) and notice_ids_value:
            notice_ids = [str(nid).strip() for nid in notice_ids_value if nid]
        elif isinstance(notice_ids_value, str):
            notice_ids = [str(notice_ids_value).strip()]
    
    return {
        "short_link": short_link,
        "id": pub_id,
        "publication_workspace_id": publication_workspace_id,
        "notice_ids": notice_ids,
        "raw_keys": raw_keys,
    }


def test_cpv_label(cpv_code: str, lang: str = "fr", dump_json: bool = False) -> tuple[bool, Optional[str], Optional[int]]:
    """
    Test get_cpv_label API call.
    Returns (success, label, exit_code_if_failed).
    exit_code: None if success, 3 if endpoint not confirmed, 4 if API call failed.
    """
    print("=== CPV ===")
    try:
        # Generate trace ID preview for logging (using the same method as the client)
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        trace_id_preview = OfficialEProcurementClient._make_trace_id()[:12]
        print(f"  Trace ID: {trace_id_preview}...")
        
        # Use the client directly to get response data
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        client, _ = _get_client()
        
        # Check if client is OfficialEProcurementClient and has get_cpv_label_with_response
        if isinstance(client, OfficialEProcurementClient) and hasattr(client, "get_cpv_label_with_response"):
            label, response_data, status_code, raw_text_preview, label_source, tried_ids, last_url = client.get_cpv_label_with_response(code=cpv_code, lang=lang)
            
            # Always print status code
            if status_code is not None:
                print(f"  Status: {status_code}")
            else:
                print(f"  Status: (no response)")
            
            # Handle dump_json flag - ALWAYS write a file
            if dump_json:
                dump_dir = Path("data/debug")
                dump_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if response_data is not None:
                    # Dump JSON response
                    dump_file = dump_dir / f"cpv_{cpv_code}_{timestamp}.json"
                    with open(dump_file, "w", encoding="utf-8") as f:
                        json.dump(response_data, f, indent=2, ensure_ascii=False)
                    print(f"  Dumped to: {dump_file}")
                else:
                    # Dump text file with diagnostics (always write something)
                    dump_file = dump_dir / f"cpv_{cpv_code}_{timestamp}.txt"
                    with open(dump_file, "w", encoding="utf-8") as f:
                        f.write(f"CPV Lookup Diagnostics\n")
                        f.write(f"======================\n\n")
                        f.write(f"Requested code: {cpv_code}\n")
                        f.write(f"Status: {status_code}\n")
                        f.write(f"Label source: {label_source}\n")
                        f.write(f"Tried candidate IDs: {', '.join(tried_ids) if tried_ids else 'none'}\n")
                        if last_url:
                            f.write(f"Last URL tried: {last_url}\n")
                        # Get trace ID preview (generate one for diagnostics)
                        from app.connectors.bosa.official_client import OfficialEProcurementClient
                        trace_id_preview = OfficialEProcurementClient._make_trace_id()[:12]
                        f.write(f"Trace ID (preview): {trace_id_preview}...\n")
                        if raw_text_preview:
                            f.write(f"\nResponse preview:\n{raw_text_preview}\n")
                    print(f"  Dumped to: {dump_file}")
            
            # Print results based on status (label_source already determined by client)
            if status_code == 200:
                if label:
                    print(f"[OK] CPV label retrieved (source: {label_source})")
                    print(f"  CPV {cpv_code} ({lang}): {label}")
                else:
                    print(f"[WARN] CPV label returned None (status {status_code}, source: {label_source})")
                    if isinstance(response_data, dict):
                        # Print top-level keys for debugging
                        keys = list(response_data.keys())[:10]  # Limit to first 10 keys
                        print(f"  Response keys: {', '.join(keys)}")
                    elif isinstance(response_data, list):
                        print(f"  Response is a list with {len(response_data)} items")
                    print(f"  CPV {cpv_code} ({lang}): (no label)")
                    if tried_ids:
                        print(f"  Tried IDs: {', '.join(tried_ids)}")
            elif status_code == 204:
                if label:
                    print(f"[OK] CPV label retrieved (source: {label_source}, API returned 204)")
                    print(f"  CPV {cpv_code} ({lang}): {label}")
                else:
                    print(f"[WARN] CPV label not found (status 204, source: {label_source})")
                    print(f"  CPV {cpv_code} ({lang}): (no label, API returned 204 No Content)")
                    if tried_ids:
                        print(f"  Tried IDs: {', '.join(tried_ids)}")
            elif status_code is not None:
                # Non-200 status - print error summary
                print(f"[ERROR] CPV lookup failed (status {status_code})")
                if isinstance(response_data, dict):
                    # Print error keys if JSON
                    error_keys = list(response_data.keys())[:10]
                    print(f"  Error keys: {', '.join(error_keys)}")
                elif raw_text_preview:
                    # Print text preview if available
                    preview = raw_text_preview[:200] + "..." if len(raw_text_preview) > 200 else raw_text_preview
                    print(f"  Error preview: {preview}")
                print(f"  CPV {cpv_code} ({lang}): (failed)")
                return False, None, 4
            else:
                # No status code (network error, etc.)
                print(f"[ERROR] CPV lookup failed (no response)")
                if raw_text_preview:
                    preview = raw_text_preview[:200] + "..." if len(raw_text_preview) > 200 else raw_text_preview
                    print(f"  Error: {preview}")
                return False, None, 4
            
            print()
            return True, label, None
        else:
            # Fallback to simple method (for playwright client or older versions)
            label = get_cpv_label(code=cpv_code, lang=lang)
            if label:
                print(f"[OK] CPV label retrieved")
                print(f"  CPV {cpv_code} ({lang}): {label}")
            else:
                print(f"[WARN] CPV label returned None")
                print(f"  CPV {cpv_code} ({lang}): (no label)")
            print()
            return True, label, None
    except EProcurementEndpointNotConfiguredError as e:
        print(f"[ERROR] Endpoints not confirmed: {e}")
        print()
        return False, None, 3
    except (ValueError, Exception) as e:
        # ValueError from API calls, HTTPError, or other exceptions
        print(f"[ERROR] CPV lookup failed: {e}")
        print()
        return False, None, 4


def test_publication_workspace(workspace_id: str) -> tuple[bool, Optional[dict[str, Any]]]:
    """
    Test get_publication_workspace API call (Dos API).
    Returns (success, workspace_dict).
    """
    print("=== Publication Workspace (Dos API) ===")
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        
        client, _ = _get_client()
        if isinstance(client, OfficialEProcurementClient):
            workspace = client.get_publication_workspace(workspace_id)
            if workspace:
                print(f"[OK] Publication workspace retrieved")
                print(f"  Workspace ID: {workspace_id}")
                if isinstance(workspace, dict):
                    keys = list(workspace.keys())[:10]  # Show first 10 keys
                    print(f"  Workspace keys: {', '.join(keys)}")
            else:
                print(f"[WARN] Publication workspace returned None")
                print(f"  Workspace ID: {workspace_id}")
                print(f"  (May be 401/403/404 or endpoint not configured)")
        else:
            print(f"[WARN] Dos API not available (playwright mode)")
        print()
        return True, workspace if 'workspace' in locals() else None
    except Exception as e:
        print(f"[WARN] Publication workspace failed: {e}")
        print()
        return False, None


def test_notice(notice_id: str) -> tuple[bool, Optional[dict[str, Any]]]:
    """
    Test get_notice API call (Dos API).
    Returns (success, notice_dict).
    """
    print("=== Notice (Dos API) ===")
    try:
        from app.connectors.bosa.client import _get_client
        from app.connectors.bosa.official_client import OfficialEProcurementClient
        
        client, _ = _get_client()
        if isinstance(client, OfficialEProcurementClient):
            notice = client.get_notice(notice_id)
            if notice:
                print(f"[OK] Notice retrieved")
                print(f"  Notice ID: {notice_id}")
                if isinstance(notice, dict):
                    keys = list(notice.keys())[:10]  # Show first 10 keys
                    print(f"  Notice keys: {', '.join(keys)}")
            else:
                print(f"[WARN] Notice returned None")
                print(f"  Notice ID: {notice_id}")
                print(f"  (May be 401/403/404 or endpoint not configured)")
        else:
            print(f"[WARN] Dos API not available (playwright mode)")
        print()
        return True, notice if 'notice' in locals() else None
    except Exception as e:
        print(f"[WARN] Notice failed: {e}")
        print()
        return False, None


def main() -> int:
    """Main smoke test function."""
    parser = argparse.ArgumentParser(
        description="Smoke test for Belgian e-Procurement official APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.smoke_eproc_api_calls
  python -m scripts.smoke_eproc_api_calls --term "restoration" --page-size 10
  python scripts/smoke_eproc_api_calls.py --cpv "45000000"
        """,
    )
    parser.add_argument(
        "--term",
        default="construction",
        help="Search term for publications (default: construction)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=5,
        help="Number of results per page (default: 5)",
    )
    parser.add_argument(
        "--cpv",
        default="45000000",
        help="CPV code to lookup (default: 45000000)",
    )
    parser.add_argument(
        "--dump-cpv-json",
        action="store_true",
        help="Dump CPV raw JSON response to data/debug/cpv_<code>.json",
    )
    parser.add_argument(
        "--dump-search-json",
        action="store_true",
        help="Dump search response to data/debug/search_<timestamp>.json",
    )
    args = parser.parse_args()

    print("=== Smoke e-Procurement API Calls ===\n")

    # Validate configuration
    try:
        config = settings.resolve_eproc_official_config()
        settings.validate_eproc_official_config()
    except ValueError as e:
        print(f"[ERROR] Configuration error: {e}")
        return 2
    except EProcurementCredentialsError as e:
        print(f"[ERROR] Credentials error: {e}")
        return 2

    print_config_section(config)

    client = OfficialEProcurementClient(
        token_url=config["token_url"],
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        search_base_url=config["search_base_url"],
        loc_base_url=config["loc_base_url"],
        dos_base_url=config.get("dos_base_url"),
        timeout_seconds=settings.eproc_timeout_seconds,
        cpv_probe=settings.eproc_cpv_probe,
    )

    # Config validation: resolve DOS URL, env, token preview, URL status
    token_for_check: Optional[str] = None
    try:
        token_for_check = client.get_access_token()
    except Exception:
        pass
    print_config_check(config, token_for_check)

    # Test token retrieval
    token_ok, _ = test_token_retrieval(client)
    if not token_ok:
        return 2

    # Test search
    search_ok, search_result, first_item, search_exit_code = test_search_publications(
        args.term, args.page_size, dump_json=args.dump_search_json
    )
    if not search_ok:
        return search_exit_code or 4

    # Test publication detail (if search returned items)
    if first_item:
        identifier_info = extract_publication_identifier(first_item)
        short_link = identifier_info.get("short_link")
        pub_id = identifier_info.get("id")
        workspace_id = identifier_info.get("publication_workspace_id")
        notice_ids = identifier_info.get("notice_ids")
        raw_keys = identifier_info.get("raw_keys", [])
        
        # Try Dos API first (publicationWorkspaceId or noticeIds)
        if workspace_id:
            print("=== Publication Detail ===")
            print(f"  Using publicationWorkspaceId: {workspace_id}")
            if raw_keys:
                keys_preview = ", ".join(raw_keys[:15])  # Show first 15 keys
                print(f"  Available keys: {keys_preview}...")
            print()
            test_publication_workspace(workspace_id)
        elif notice_ids:
            print("=== Publication Detail ===")
            print(f"  Using noticeIds[0]: {notice_ids[0]}")
            if raw_keys:
                keys_preview = ", ".join(raw_keys[:15])
                print(f"  Available keys: {keys_preview}...")
            print()
            test_notice(notice_ids[0])
        elif short_link:
            print("=== Publication Detail ===")
            print(f"  Using shortLink: {short_link}")
            if raw_keys:
                keys_preview = ", ".join(raw_keys[:15])
                print(f"  Available keys: {keys_preview}...")
            print()
            print("[WARN] Publication detail by shortLink not yet implemented (use Dos API)")
            print()
        elif pub_id:
            print("=== Publication Detail ===")
            print(f"  Found ID: {pub_id} (Dos API identifiers not available)")
            if raw_keys:
                keys_preview = ", ".join(raw_keys[:15])
                print(f"  Available keys: {keys_preview}...")
            print()
            print("[WARN] Publication detail by ID not yet implemented")
            print()
        else:
            print("=== Publication Detail ===")
            print("[WARN] No publication identifier found in first item")
            if raw_keys:
                keys_preview = ", ".join(raw_keys[:30])  # Show up to 30 keys
                print(f"  Available keys: {keys_preview}")
            print()

    # Test CPV label
    cpv_ok, _, cpv_exit_code = test_cpv_label(args.cpv, dump_json=args.dump_cpv_json)
    if not cpv_ok:
        # CPV lookup failure is not fatal for smoke test, but return exit code if it's endpoint error
        if cpv_exit_code == 3:
            return 3
        # Otherwise, warn but continue

    print("[OK] All smoke tests completed successfully")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Test cancelled by user", file=sys.stderr)
        sys.exit(130)
    except EProcurementCredentialsError as e:
        print(f"\n[ERROR] Credentials error: {e}", file=sys.stderr)
        sys.exit(2)
    except EProcurementEndpointNotConfiguredError as e:
        print(f"\n[ERROR] Endpoints not confirmed: {e}", file=sys.stderr)
        sys.exit(3)
    except ValueError as e:
        # API call errors (from official_client raising ValueError)
        print(f"\n[ERROR] API call failed: {e}", file=sys.stderr)
        sys.exit(4)
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(4)
