#!/usr/bin/env python3
"""Discover BOSA e-Procurement Search API (Sea) endpoints from Swagger and optionally test."""
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.connectors.bosa.official_client import OfficialEProcurementClient


def find_search_endpoints(swagger: dict) -> list[dict]:
    """Find endpoints that contain 'publication', 'bda', or 'search' in path/summary/operationId."""
    endpoints = []
    paths = swagger.get("paths", {})
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId", "").lower()
            summary = (operation.get("summary") or "").lower()
            path_lower = path.lower()
            if any(
                keyword in path_lower or keyword in operation_id or keyword in summary
                for keyword in ("publication", "bda", "search")
            ):
                endpoints.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "operationId": operation.get("operationId", ""),
                        "summary": operation.get("summary", ""),
                    }
                )
    return endpoints


def test_search_endpoint(client: OfficialEProcurementClient, base_url: str, endpoint: dict) -> dict:
    """Test a search endpoint with a simple query."""
    method = endpoint["method"]
    path = endpoint["path"]
    url = f"{base_url.rstrip('/')}{path}"

    # Try common query parameter names
    test_params = {"term": "travaux", "page": 1, "pageSize": 10}
    if method == "GET":
        try:
            response = client.request(method, url, params=test_params, timeout=30)
            response.raise_for_status()
            data = response.json()
            count = 0
            if isinstance(data, dict):
                count = len(data.get("items", data.get("results", data.get("data", []))))
            elif isinstance(data, list):
                count = len(data)
            return {"status": response.status_code, "items_count": count}
        except Exception as e:
            return {"status": getattr(e.response, "status_code", None) if hasattr(e, "response") else None, "error": str(e)}
    else:
        # POST/PUT: try JSON body
        try:
            response = client.request(method, url, json_data=test_params, timeout=30)
            response.raise_for_status()
            data = response.json()
            count = 0
            if isinstance(data, dict):
                count = len(data.get("items", data.get("results", data.get("data", []))))
            elif isinstance(data, list):
                count = len(data)
            return {"status": response.status_code, "items_count": count}
        except Exception as e:
            return {"status": getattr(e.response, "status_code", None) if hasattr(e, "response") else None, "error": str(e)}


def main() -> int:
    """Main discovery script."""
    env = settings.eprocurement_env.upper()
    sea_base_url = settings.bosa_sea_base_url
    token_url = settings.bosa_token_url
    client_id = settings.bosa_client_id
    client_secret = settings.bosa_client_secret
    endpoint_confirmed = settings.eprocurement_endpoint_confirmed

    print(f"Environment: {env}")
    print(f"Search API base URL: {sea_base_url}")
    print(f"Token URL: {token_url}")

    if not client_id or not client_secret:
        print("ERROR: Client ID or Client Secret not configured")
        print(f"  Set EPROCUREMENT_{env}_CLIENT_ID and EPROCUREMENT_{env}_CLIENT_SECRET in .env")
        return 1

    # Build swagger URL
    swagger_url = f"{sea_base_url.rstrip('/')}/doc/swagger_json"
    print(f"\nSwagger URL: {swagger_url}")

    # Create client
    client = OfficialEProcurementClient(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        search_base_url=sea_base_url,
        timeout_seconds=30,
    )

    # Discover swagger
    try:
        print("\nDownloading swagger...")
        swagger = client.discover_openapi(swagger_url)
        print("Swagger downloaded and cached")
    except Exception as e:
        print(f"ERROR: Failed to download swagger: {e}")
        return 1

    # Find search endpoints
    endpoints = find_search_endpoints(swagger)
    print(f"\nFound {len(endpoints)} candidate endpoints:")
    for i, ep in enumerate(endpoints, 1):
        print(f"  {i}. {ep['method']} {ep['path']}")
        if ep.get("summary"):
            print(f"     Summary: {ep['summary']}")
        if ep.get("operationId"):
            print(f"     OperationId: {ep['operationId']}")

    # Test endpoint if confirmed
    if endpoint_confirmed and endpoints:
        print(f"\nEPROCUREMENT_ENDPOINT_CONFIRMED=true, testing first endpoint...")
        test_result = test_search_endpoint(client, sea_base_url, endpoints[0])
        if "error" in test_result:
            print(f"  ERROR: {test_result['error']}")
            if test_result.get("status"):
                print(f"  HTTP Status: {test_result['status']}")
        else:
            print(f"  HTTP Status: {test_result['status']}")
            print(f"  Items count: {test_result['items_count']}")
    else:
        print("\nEPROCUREMENT_ENDPOINT_CONFIRMED=false (or no endpoints found)")
        print("Set EPROCUREMENT_ENDPOINT_CONFIRMED=true in .env to enable endpoint testing")
        return 0

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
