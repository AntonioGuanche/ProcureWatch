"""OpenAPI/Swagger discovery for TED (Tenders Electronic Daily) Search API."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# Cache file path relative to project root
CACHE_REL_PATH = Path("data") / "_cache" / "ted_endpoints.json"

# Candidate spec URLs (path suffixes) to try on the API host, in order.
# Primary: official docs at ted.europa.eu/api/documentation/; then common swagger patterns.
SPEC_CANDIDATE_PATHS = [
    "/api/documentation/api-docs",
    "/api/documentation/v3/api-docs",
    "/api/documentation/openapi.json",
    "/api-docs",
    "/v3/api-docs",
    "/openapi.json",
    "/swagger.json",
    "/swagger/v1/swagger.json",
    "/swagger-ui/swagger-config",
    "/swagger-ui/index.html",
]
BODY_SNIPPET_LEN = 500

# Parameter name aliases for search
TERM_PARAM_ALIASES = ["query", "term", "q", "search"]
PAGE_PARAM_ALIASES = ["page"]
PAGE_SIZE_PARAM_ALIASES = ["limit", "pageSize", "page_size", "size"]


class TEDDiscoveryError(Exception):
    """Raised when the OpenAPI spec cannot be found or search endpoint cannot be discovered."""

    pass


def _project_root() -> Path:
    """Return project root (parent of connectors)."""
    return Path(__file__).resolve().parent.parent.parent


def _cache_path() -> Path:
    return _project_root() / CACHE_REL_PATH


def _iter_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield (method, path, operation) for OpenAPI 2.0 and 3.x. path includes basePath for OAS2."""
    paths = spec.get("paths", {})
    base_path = (spec.get("basePath") or "").rstrip("/")
    if base_path and not base_path.startswith("/"):
        base_path = "/" + base_path
    # OpenAPI 3 servers might override; we use basePath for simplicity
    result: list[tuple[str, str, dict[str, Any]]] = []
    for path_pattern, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_with_base = path_pattern if path_pattern.startswith("/") else f"/{path_pattern}"
        full_path = (base_path + path_with_base) if base_path else path_with_base
        for method in ["get", "post", "put", "patch", "delete"]:
            op = path_item.get(method)
            if isinstance(op, dict):
                result.append((method.upper(), full_path, op))
    return result


def _params_for_operation(operation: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Get list of parameter definitions (OpenAPI 2 and 3)."""
    params = list(operation.get("parameters") or [])
    resolved = []
    for p in params:
        if isinstance(p, dict):
            resolved.append(p)
        elif isinstance(p, str) and p.startswith("#/"):
            parts = p.replace("#/", "").split("/")
            cur = spec
            for part in parts:
                cur = cur.get(part, {})
            if isinstance(cur, dict):
                resolved.append(cur)
    return resolved


def _request_body_schema(operation: dict[str, Any], spec: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Get requestBody schema for OpenAPI 3, or body param for OpenAPI 2."""
    body = operation.get("requestBody")
    if body and isinstance(body, dict):
        content = body.get("content", {})
        json_media = content.get("application/json") or content.get("application/json; charset=utf-8")
        if isinstance(json_media, dict):
            schema = json_media.get("schema")
            if isinstance(schema, dict):
                return schema
    for p in operation.get("parameters") or []:
        if isinstance(p, dict) and p.get("in") == "body" and p.get("schema"):
            return p["schema"]
    return None


def _schema_property_names(schema: Optional[dict[str, Any]]) -> set[str]:
    if not schema:
        return set()
    props = schema.get("properties")
    if isinstance(props, dict):
        return set(props.keys())
    return set()


def _get_spec_url_from_swagger_config(data: dict[str, Any], base: str) -> Optional[str]:
    """Parse swagger-config JSON to find the spec URL."""
    url = data.get("url")
    if isinstance(url, str) and url.strip():
        return urljoin(base, url.strip())
    urls = data.get("urls")
    if isinstance(urls, list) and urls:
        first = urls[0]
        if isinstance(first, dict) and first.get("url"):
            return urljoin(base, first["url"])
        if isinstance(first, str):
            return urljoin(base, first)
    return None


def _get_spec_url_from_swagger_html(html: str, base: str) -> Optional[str]:
    """Parse Swagger UI index HTML for url: or urls: to find spec URL."""
    if not html or not isinstance(html, str):
        return None
    # Common pattern: url: "https://...", or url: "/v3/api-docs"
    m = re.search(r'url\s*:\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return urljoin(base, m.group(1).strip())
    m = re.search(r'urls\s*:\s*\[\s*\{\s*url\s*:\s*["\']([^"\']+)["\']', html, re.IGNORECASE | re.DOTALL)
    if m:
        return urljoin(base, m.group(1).strip())
    return None


def fetch_spec(host: str, timeout: int = 30) -> tuple[dict[str, Any], list[str]]:
    """
    Try candidate spec URLs on host; return (parsed_spec, list_of_tried_urls).
    Raises TEDDiscoveryError if no candidate returns a valid OpenAPI spec.
    Error message includes tried URLs and last response status/body snippet.
    """
    host = (host or "").rstrip("/")
    if not host.startswith("http"):
        host = "https://" + host
    tried: list[str] = []
    last_status: Optional[int] = None
    last_body_snippet: str = ""

    for path in SPEC_CANDIDATE_PATHS:
        url = urljoin(host, path)
        tried.append(url)
        try:
            resp = requests.get(url, timeout=timeout)
            last_status = resp.status_code
            last_body_snippet = (resp.text or "")[:BODY_SNIPPET_LEN]
            if resp.status_code != 200:
                continue
            ct = (resp.headers.get("Content-Type") or "").lower()
            if "json" in ct:
                data = resp.json()
                if path == "/swagger-ui/swagger-config":
                    spec_url = _get_spec_url_from_swagger_config(data, host)
                    if spec_url:
                        tried.append(spec_url)
                        spec_resp = requests.get(spec_url, timeout=timeout)
                        last_status = spec_resp.status_code
                        last_body_snippet = (spec_resp.text or "")[:BODY_SNIPPET_LEN]
                        if spec_resp.status_code == 200:
                            return spec_resp.json(), tried
                    continue
                if isinstance(data, dict) and data.get("paths") is not None:
                    return data, tried
            if path == "/swagger-ui/index.html" and "text/html" in ct:
                spec_url = _get_spec_url_from_swagger_html(resp.text, host)
                if spec_url:
                    tried.append(spec_url)
                    spec_resp = requests.get(spec_url, timeout=timeout)
                    last_status = spec_resp.status_code
                    last_body_snippet = (spec_resp.text or "")[:BODY_SNIPPET_LEN]
                    if spec_resp.status_code == 200:
                        try:
                            return spec_resp.json(), tried
                        except ValueError:
                            pass
        except requests.RequestException:
            continue
        except ValueError:
            continue

    msg = (
        "Could not find a valid OpenAPI spec for TED. Tried: " + ", ".join(tried)
    )
    if last_status is not None:
        msg += f". Last response status: {last_status}"
    if last_body_snippet:
        msg += f". Last body snippet: {last_body_snippet!r}"
    raise TEDDiscoveryError(msg)


@dataclass
class SearchCandidate:
    """A candidate 'search notices' endpoint from the spec."""

    method: str
    path: str
    operation_id: str
    summary: str
    score: float
    style: str  # "json_body" | "query_params"
    term_param: Optional[str]
    page_param: Optional[str]
    page_size_param: Optional[str]


def discover_search_notices_endpoint(spec: dict[str, Any]) -> list[SearchCandidate]:
    """
    Discover candidates for "search notices": paths containing "notices" AND "search"
    (or tagged Search/search), POST or GET. Score higher for term/query and pagination params.
    """
    candidates: list[SearchCandidate] = []
    for method, path, operation in _iter_operations(spec):
        path_lower = path.lower()
        tags = [t.lower() for t in (operation.get("tags") or []) if isinstance(t, str)]
        has_search_tag = any("search" in t for t in tags)
        if not has_search_tag and ("notices" not in path_lower or "search" not in path_lower):
            continue
        if method not in ("POST", "GET"):
            continue

        op_id = (operation.get("operationId") or "").lower()
        summary = (operation.get("summary") or "").lower()
        params = _params_for_operation(operation, spec)
        param_names = {p.get("name", "").lower(): p.get("name") for p in params if p.get("name")}
        body_schema = _request_body_schema(operation, spec)
        body_props = _schema_property_names(body_schema)
        all_names = set(param_names.keys()) | {k.lower() for k in body_props}

        term_param = None
        for alias in TERM_PARAM_ALIASES:
            if alias.lower() in param_names:
                term_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in all_names:
                term_param = next((k for k in body_props if k.lower() == alias.lower()), alias)
                break
        page_param = None
        for alias in PAGE_PARAM_ALIASES:
            if alias.lower() in param_names:
                page_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in all_names:
                page_param = next((k for k in body_props if k.lower() == alias.lower()), alias)
                break
        page_size_param = None
        for alias in PAGE_SIZE_PARAM_ALIASES:
            if alias.lower() in param_names:
                page_size_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in all_names:
                page_size_param = next((k for k in body_props if k.lower() == alias.lower()), alias)
                break

        style = "query_params"
        if body_schema or method == "POST":
            style = "json_body"

        score = 10.0
        if term_param:
            score += 3.0
        if page_param:
            score += 1.0
        if page_size_param:
            score += 1.0
        if "search" in op_id or "search" in summary:
            score += 2.0
        if has_search_tag:
            score += 1.0
        if method == "POST" and style == "json_body":
            score += 1.0

        candidates.append(
            SearchCandidate(
                method=method,
                path=path,
                operation_id=operation.get("operationId") or "",
                summary=operation.get("summary") or "",
                score=score,
                style=style,
                term_param=term_param,
                page_param=page_param,
                page_size_param=page_size_param,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _candidate_to_descriptor(c: SearchCandidate, base_url: str) -> dict[str, Any]:
    """Build cache descriptor from best candidate."""
    return {
        "base_url": base_url.rstrip("/"),
        "path": c.path,
        "method": c.method,
        "style": c.style,
        "term_param": c.term_param or "query",
        "page_param": c.page_param or "page",
        "page_size_param": c.page_size_param or "limit",
    }


def load_or_discover_endpoints(
    force: bool = False,
    host: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Load search endpoint descriptor from cache or run discovery and cache result.
    If force=True, always run discovery and overwrite cache.
    host: API host (e.g. https://api.ted.europa.eu). Default from settings if None.
    Returns descriptor: base_url, path, method, style, term_param, page_param, page_size_param.
    Raises TEDDiscoveryError if discovery fails (no spec or no search endpoint).
    """
    cache_file = _cache_path()
    if not force and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("path") and data.get("base_url"):
                return data
        except Exception as e:
            logger.warning("Failed to load TED endpoints cache: %s; running discovery", e)

    if host is None:
        from app.core.config import settings
        host = getattr(settings, "ted_search_base_url", "https://ted.europa.eu") or "https://ted.europa.eu"

    spec, tried = fetch_spec(host, timeout=timeout)
    candidates = discover_search_notices_endpoint(spec)
    if not candidates:
        raise TEDDiscoveryError(
            "OpenAPI spec was found but no 'search notices' endpoint could be discovered "
            "(paths containing 'notices' and 'search'). Tried spec URLs: " + ", ".join(tried)
        )

    best = candidates[0]
    base_url = host.rstrip("/")
    descriptor = _candidate_to_descriptor(best, base_url)
    descriptor["updated_at"] = datetime.now(timezone.utc).isoformat()

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(descriptor, f, indent=2)
    logger.info("TED discovered endpoints written to %s", cache_file)
    return descriptor
