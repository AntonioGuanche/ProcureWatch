"""OpenAPI/Swagger discovery for Belgian e-Procurement SEA and LOC APIs."""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# Default swagger URLs (configurable via settings)
DEFAULT_SEA_SWAGGER_URL = "https://public.int.fedservices.be/api/eProcurementSea/v1/doc/swagger.json"
DEFAULT_LOC_SWAGGER_URL = "https://public.int.fedservices.be/api/eProcurementLoc/v1/doc/swagger.json"

# Cache file path relative to project root (standardized Windows-safe path)
CACHE_REL_PATH = Path("data") / "cache" / "eprocurement_endpoints_confirmed.json"

# Heuristic keywords for search publications endpoint
SEARCH_POSITIVE_KEYWORDS = ["publication", "publications", "bda", "search"]
SEARCH_NEGATIVE_KEYWORDS = ["shop"]
SEARCH_SHORTLINK_NEGATIVE = ["short link", "shortlink"]  # in summary/description -> exclude or penalize
SEARCH_PARAM_TERM_ALIASES = ["terms", "term", "query", "q"]
SEARCH_PARAM_PAGE_ALIASES = ["page"]
SEARCH_PARAM_PAGE_SIZE_ALIASES = ["pageSize", "page_size", "size", "limit"]

# Scoring: penalties for wrong endpoint types (GET /search/publications is the confirmed winner)
PENALTY_PATH_GENERATE_SHORT_LINK = -100  # path contains generateShortLink
PENALTY_PATH_BY_SHORT_LINK = -100  # path contains byShortLink
PENALTY_PATH_SHORT_LINK = -50  # path contains shortLink (other)
BONUS_EXACT_PATH_SEARCH_PUBLICATIONS = 20  # path ends with /search/publications
BONUS_GET_QUERY_PARAMS = 5  # prefer GET with query params when both GET and POST /search/publications exist
BONUS_RESPONSE_HAS_PUBLICATIONS = 10  # response schema suggests list of publications/items/results

# Heuristic keywords for CPV label endpoint
CPV_POSITIVE_KEYWORDS = ["cpv"]
CPV_PARAM_CODE_ALIASES = ["code", "cpvCode", "cpv_code"]
CPV_PARAM_LANG_ALIASES = ["language", "lang", "locale"]

# Publication detail: path with /publications and {id} or {publicationId}, GET
DETAIL_PATH_ID_PATTERNS = ["id", "publicationid", "publication-id"]


@dataclass
class CandidateEndpoint:
    """A candidate endpoint discovered from OpenAPI spec."""

    method: str
    path: str
    operation_id: str
    summary: str
    score: float
    style: str  # "json_body" or "query_params"
    term_param: Optional[str] = None
    page_param: Optional[str] = None
    page_size_param: Optional[str] = None
    code_param: Optional[str] = None
    lang_param: Optional[str] = None
    path_params: list[str] = field(default_factory=list)
    score_reasons: list[str] = field(default_factory=list)  # bonuses/penalties applied


@dataclass
class DiscoveredEndpoints:
    """Cached discovered endpoints for search, CPV, and publication detail."""

    search_publications: dict[str, Any]
    cpv_label: dict[str, Any]
    publication_detail: dict[str, Any]
    updated_at: str

    def search_method(self) -> str:
        return self.search_publications.get("method", "POST").upper()

    def search_path(self) -> str:
        return self.search_publications.get("path", "")

    def search_style(self) -> str:
        return self.search_publications.get("style", "json_body")

    def cpv_method(self) -> str:
        return self.cpv_label.get("method", "GET").upper()

    def cpv_path(self) -> str:
        return self.cpv_label.get("path", "")

    def publication_detail_path(self) -> str:
        return self.publication_detail.get("path", "")

    def publication_detail_id_param(self) -> str:
        return self.publication_detail.get("id_param", "id")


def discover_publication_detail_endpoint(spec: dict[str, Any]) -> list[CandidateEndpoint]:
    """
    Discover candidates for "publication detail" (single publication by ID) from SEA spec.
    Prefer GET paths containing /publications and {id} or {publicationId}; score higher for "detail".
    """
    candidates: list[CandidateEndpoint] = []
    for method, path, operation in _iter_operations(spec):
        path_lower = path.lower()
        if "/publications" not in path_lower:
            continue
        if method != "GET":
            continue
        params = _params_for_operation(operation, spec)
        path_params = [p.get("name") for p in params if p.get("in") == "path" and p.get("name")]
        if not path_params and "{" in path:
            path_params = re.findall(r"\{(\w+)\}", path)
        if not path_params:
            continue
        id_param = None
        for p in path_params:
            if (p or "").lower().replace("-", "") in ("id", "publicationid"):
                id_param = p
                break
        if not id_param and path_params:
            id_param = path_params[0]

        op_id = (operation.get("operationId") or "").lower()
        summary = (operation.get("summary") or "").lower()
        text = f"{op_id} {summary} {path_lower}"
        score = 5.0
        if "publication" in text:
            score += 2.0
        if "detail" in text or "get" in op_id:
            score += 3.0
        if id_param and (id_param.lower() == "id" or "publication" in id_param.lower()):
            score += 2.0

        candidates.append(
            CandidateEndpoint(
                method=method,
                path=path,
                operation_id=operation.get("operationId") or "",
                summary=operation.get("summary") or "",
                score=score,
                style="query_params",
                term_param=None,
                page_param=None,
                page_size_param=None,
                code_param=None,
                lang_param=None,
                path_params=path_params,
                score_reasons=[],
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _publication_detail_to_cache(c: CandidateEndpoint) -> dict[str, Any]:
    """Build cache entry for publication detail; id_param is the path param name for substitution."""
    id_param = None
    for p in c.path_params:
        if (p or "").lower().replace("-", "") in ("id", "publicationid"):
            id_param = p
            break
    if not id_param and c.path_params:
        id_param = c.path_params[0]
    return {
        "method": c.method,
        "path": c.path,
        "id_param": id_param or "id",
        "path_params": c.path_params,
    }


def _project_root() -> Path:
    """Return project root (parent of connectors)."""
    return Path(__file__).resolve().parent.parent.parent


def cache_path() -> Path:
    """Get the endpoints cache file path (Windows-safe absolute)."""
    return _project_root() / CACHE_REL_PATH


def cache_path() -> Path:
    """Return absolute path to endpoints cache file (public API)."""
    return _project_root() / CACHE_REL_PATH


def _cache_path() -> Path:
    """Return absolute path to endpoints cache file (internal, use cache_path())."""
    return cache_path()


def download_swagger(url: str, timeout: int = 30) -> dict[str, Any]:
    """Download and parse swagger.json from URL."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _iter_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """
    Yield (method, path, operation) for OpenAPI 2.0 and 3.x.
    path is full path (basePath + path for OpenAPI 2).
    """
    paths = spec.get("paths", {})
    base_path = (spec.get("basePath") or "").rstrip("/")
    if base_path and not base_path.startswith("/"):
        base_path = "/" + base_path

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


def iter_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """List (method, path, operation) for all operations in spec. For use by scripts (e.g. list exclusions)."""
    return _iter_operations(spec)


def _params_for_operation(operation: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Get list of parameter definitions (OpenAPI 2 and 3)."""
    params = list(operation.get("parameters") or [])
    # Resolve $ref in parameters (OpenAPI 3)
    resolved = []
    for p in params:
        if isinstance(p, dict):
            resolved.append(p)
        elif isinstance(p, str) and p.startswith("#/"):
            # Simple ref resolve
            parts = p.replace("#/", "").split("/")
            cur = spec
            for part in parts:
                cur = cur.get(part, {})
            if isinstance(cur, dict):
                resolved.append(cur)
    return resolved


def _request_body_schema(operation: dict[str, Any], spec: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Get requestBody schema for OpenAPI 3, or body param schema for OpenAPI 2."""
    # OpenAPI 3
    body = operation.get("requestBody")
    if body and isinstance(body, dict):
        content = body.get("content", {})
        json_media = content.get("application/json") or content.get("application/json; charset=utf-8")
        if isinstance(json_media, dict):
            schema = json_media.get("schema")
            if isinstance(schema, dict):
                return schema
    # OpenAPI 2: single parameter with in=body and schema
    for p in operation.get("parameters") or []:
        if isinstance(p, dict) and p.get("in") == "body" and p.get("schema"):
            return p["schema"]
    return None


def _schema_property_names(schema: Optional[dict[str, Any]]) -> set[str]:
    """Extract property names from a JSON schema (for body params)."""
    if not schema:
        return set()
    props = schema.get("properties")
    if isinstance(props, dict):
        return set(props.keys())
    return set()


def _response_schema(operation: dict[str, Any], spec: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Get 200 response schema (OpenAPI 2 and 3)."""
    responses = operation.get("responses") or {}
    r200 = responses.get("200") or responses.get("200")
    if not isinstance(r200, dict):
        return None
    # OpenAPI 3: content.application/json.schema
    content = r200.get("content", {})
    if content:
        json_media = content.get("application/json") or content.get("application/json; charset=utf-8")
        if isinstance(json_media, dict):
            schema = json_media.get("schema")
            if isinstance(schema, dict):
                return schema
    # OpenAPI 2: schema directly
    schema = r200.get("schema")
    if isinstance(schema, dict):
        return schema
    return None


def _response_schema_suggests_publications(schema: Optional[dict[str, Any]]) -> bool:
    """True if schema suggests a list of publications/items (array or properties like publications, items, results, total)."""
    if not schema:
        return False
    if schema.get("type") == "array":
        return True
    props = schema.get("properties")
    if isinstance(props, dict):
        keys_lower = {str(k).lower() for k in props.keys()}
        if any(k in keys_lower for k in ("publications", "items", "results", "total")):
            return True
    return False


def _is_shortlink_or_generate_shortlink(path: str, summary: str) -> bool:
    """
    Response-shape heuristic (no network): exclude endpoints that return a shortlink
    rather than publications. Returns True if this candidate should be excluded.
    """
    path_lower = path.lower()
    summary_lower = (summary or "").lower()
    if "generateshortlink" in path_lower:
        return True
    if "generate" in path_lower and "shortlink" in path_lower:
        return True
    if "short link" in summary_lower or "shortlink" in summary_lower:
        return True
    return False


def is_shortlink_candidate(path: str, summary: str) -> bool:
    """True if this path/summary would be excluded from search_publications (shortlink)."""
    if "generateshortlink" in (path or "").lower():
        return True
    return _is_shortlink_or_generate_shortlink(path or "", summary or "")


def discover_search_publications_endpoint(spec: dict[str, Any]) -> list[CandidateEndpoint]:
    """
    Discover candidates for "search publications" from SEA swagger spec.
    Heuristics: path/operationId/summary contains publication/publications/bda/search,
    prefer params: terms/term/query, page, pageSize. Excludes and penalizes shortlink endpoints.
    """
    candidates: list[CandidateEndpoint] = []
    for method, path, operation in _iter_operations(spec):
        path_lower = path.lower()
        # Explicit blacklist: any path containing generateShortLink is never a search_publications candidate
        if "generateshortlink" in path_lower:
            continue

        op_id = operation.get("operationId") or ""
        summary = operation.get("summary") or ""
        description = (operation.get("description") or "").lower()
        op_id_lower = op_id.lower()
        summary_lower = summary.lower()
        text = f"{op_id_lower} {summary_lower} {description} {path_lower}"

        # Safety check: exclude endpoints that return shortlink rather than publications
        if _is_shortlink_or_generate_shortlink(path, summary):
            continue
        if "short link" in description or "shortlink" in description:
            continue

        # Must match at least one positive keyword
        if not any(k in text for k in SEARCH_POSITIVE_KEYWORDS):
            continue
        if any(k in text for k in SEARCH_NEGATIVE_KEYWORDS):
            pass

        params = _params_for_operation(operation, spec)
        param_names = {p.get("name", "").lower(): p.get("name") for p in params if p.get("name")}
        body_schema = _request_body_schema(operation, spec)
        body_props = _schema_property_names(body_schema)
        all_param_names = set(param_names.keys()) | {k.lower() for k in body_props}

        term_param = None
        for alias in SEARCH_PARAM_TERM_ALIASES:
            if alias.lower() in param_names:
                term_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in {b.lower() for b in body_props}:
                term_param = alias
                break
            if alias.lower() in all_param_names:
                term_param = alias
                break

        page_param = None
        for alias in SEARCH_PARAM_PAGE_ALIASES:
            if alias.lower() in param_names:
                page_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in all_param_names:
                page_param = alias
                break

        page_size_param = None
        for alias in SEARCH_PARAM_PAGE_SIZE_ALIASES:
            if alias.lower() in param_names:
                page_size_param = param_names[alias.lower()]
                break
            if alias in body_props or alias.lower() in all_param_names:
                page_size_param = alias
                break

        # Prefer POST with body for search (like publicprocurement.be)
        style = "query_params"
        if body_schema or method == "POST":
            style = "json_body"

        score = 0.0
        reasons: list[str] = []
        if "generateshortlink" in path_lower:
            score += PENALTY_PATH_GENERATE_SHORT_LINK
            reasons.append(f"path contains generateShortLink ({PENALTY_PATH_GENERATE_SHORT_LINK})")
        if "byshortlink" in path_lower:
            score += PENALTY_PATH_BY_SHORT_LINK
            reasons.append(f"path contains byShortLink ({PENALTY_PATH_BY_SHORT_LINK})")
        if "shortlink" in path_lower and "generateshortlink" not in path_lower and "byshortlink" not in path_lower:
            score += PENALTY_PATH_SHORT_LINK
            reasons.append(f"path contains shortLink ({PENALTY_PATH_SHORT_LINK})")
        path_normalized = path.rstrip("/")
        if path_normalized.endswith("/search/publications"):
            score += BONUS_EXACT_PATH_SEARCH_PUBLICATIONS
            reasons.append(f"exact path /search/publications (+{BONUS_EXACT_PATH_SEARCH_PUBLICATIONS})")
            # Prefer GET with query params when both GET and POST /search/publications exist
            if method == "GET" and (term_param or page_param or page_size_param):
                score += BONUS_GET_QUERY_PARAMS
                reasons.append(f"GET with query params (+{BONUS_GET_QUERY_PARAMS})")
        resp_schema = _response_schema(operation, spec)
        if _response_schema_suggests_publications(resp_schema):
            score += BONUS_RESPONSE_HAS_PUBLICATIONS
            reasons.append(f"response schema has publications/items/array (+{BONUS_RESPONSE_HAS_PUBLICATIONS})")
        if any(k in text for k in ["publication", "publications", "search"]):
            score += 2.0
            reasons.append("keywords publication/publications/search (+2)")
        if "bda" in text:
            score += 1.0
            reasons.append("keyword bda (+1)")
        if term_param:
            score += 2.0
            reasons.append("has term param (+2)")
        if page_param:
            score += 1.0
            reasons.append("has page param (+1)")
        if page_size_param:
            score += 1.0
            reasons.append("has pageSize param (+1)")
        if "shop" in text:
            score -= 2.0
            reasons.append("keyword shop (-2)")

        candidates.append(
            CandidateEndpoint(
                method=method,
                path=path,
                operation_id=op_id,
                summary=summary,
                score=score,
                style=style,
                term_param=term_param,
                page_param=page_param,
                page_size_param=page_size_param,
                code_param=None,
                lang_param=None,
                score_reasons=reasons,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    # Final sanity check: if the chosen endpoint suggests shortlink, reject and choose next best
    non_shortlink = [
        c for c in candidates
        if "generateshortlink" not in c.path.lower() and not _is_shortlink_or_generate_shortlink(c.path, c.summary)
    ]
    if non_shortlink:
        return non_shortlink
    return candidates


def discover_cpv_label_endpoint(spec: dict[str, Any]) -> list[CandidateEndpoint]:
    """
    Discover candidates for CPV code label from LOC swagger spec.
    Heuristics: path/operationId/summary contains cpv; prefer code + language/lang.
    """
    candidates: list[CandidateEndpoint] = []
    for method, path, operation in _iter_operations(spec):
        op_id = (operation.get("operationId") or "").lower()
        summary = (operation.get("summary") or "").lower()
        path_lower = path.lower()
        text = f"{op_id} {summary} {path_lower}"
        if not any(k in text for k in CPV_POSITIVE_KEYWORDS):
            continue

        params = _params_for_operation(operation, spec)
        param_names = {p.get("name", "").lower(): p.get("name") for p in params if p.get("name")}
        path_params = [p.get("name") for p in params if p.get("in") == "path" and p.get("name")]
        if not path_params and "{" in path:
            path_params = re.findall(r"\{(\w+)\}", path)

        code_param = None
        for alias in CPV_PARAM_CODE_ALIASES:
            if alias.lower() in param_names:
                code_param = param_names[alias.lower()]
                break
        if not code_param and "code" in path_lower:
            code_param = "code"
        if not code_param and path_params:
            code_param = path_params[0]

        lang_param = None
        for alias in CPV_PARAM_LANG_ALIASES:
            if alias.lower() in param_names:
                lang_param = param_names[alias.lower()]
                break

        score = 1.0
        if "cpv" in text:
            score += 2.0
        if code_param:
            score += 2.0
        if lang_param:
            score += 1.0
        if "description" in text or "label" in text:
            score += 1.0

        candidates.append(
            CandidateEndpoint(
                method=method,
                path=path,
                operation_id=operation.get("operationId") or "",
                summary=operation.get("summary") or "",
                score=score,
                style="query_params",
                term_param=None,
                page_param=None,
                page_size_param=None,
                code_param=code_param,
                lang_param=lang_param,
                path_params=path_params,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _candidate_to_search_cache(c: CandidateEndpoint) -> dict[str, Any]:
    return {
        "method": c.method,
        "path": c.path,
        "style": c.style,
        "term_param": c.term_param,
        "page_param": c.page_param,
        "page_size_param": c.page_size_param,
    }


def _candidate_to_cpv_cache(c: CandidateEndpoint) -> dict[str, Any]:
    return {
        "method": c.method,
        "path": c.path,
        "code_param": c.code_param,
        "lang_param": c.lang_param,
        "path_params": c.path_params,
    }


def load_or_discover_endpoints(
    force: bool = False,
    sea_swagger_url: Optional[str] = None,
    loc_swagger_url: Optional[str] = None,
    timeout: int = 30,
) -> DiscoveredEndpoints:
    """
    Load endpoints from cache or run discovery and cache result.
    If force=True, always run discovery and overwrite cache.
    """
    cache_file = cache_path()
    if not force and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Check if cache is confirmed (has confirmed flag and it's True)
            if data.get("confirmed", False):
                return DiscoveredEndpoints(
                    search_publications=data.get("search_publications", {}),
                    cpv_label=data.get("cpv_label", {}),
                    publication_detail=data.get("publication_detail", {}),
                    updated_at=data.get("updated_at", ""),
                )
            else:
                logger.info("Endpoints cache exists but not confirmed, running discovery")
        except Exception as e:
            logger.warning("Failed to load endpoints cache: %s; running discovery", e)

    sea_url = sea_swagger_url or DEFAULT_SEA_SWAGGER_URL
    loc_url = loc_swagger_url or DEFAULT_LOC_SWAGGER_URL

    sea_spec = download_swagger(sea_url, timeout=timeout)
    loc_spec = download_swagger(loc_url, timeout=timeout)

    search_candidates = discover_search_publications_endpoint(sea_spec)
    cpv_candidates = discover_cpv_label_endpoint(loc_spec)
    detail_candidates = discover_publication_detail_endpoint(sea_spec)

    search_ep = search_candidates[0] if search_candidates else None
    cpv_ep = cpv_candidates[0] if cpv_candidates else None
    detail_ep = detail_candidates[0] if detail_candidates else None

    search_publications = _candidate_to_search_cache(search_ep) if search_ep else {}
    cpv_label = _candidate_to_cpv_cache(cpv_ep) if cpv_ep else {}
    publication_detail = _publication_detail_to_cache(detail_ep) if detail_ep else {}

    updated_at = datetime.now(timezone.utc).isoformat()
    discovered = DiscoveredEndpoints(
        search_publications=search_publications,
        cpv_label=cpv_label,
        publication_detail=publication_detail,
        updated_at=updated_at,
    )

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "confirmed": True,  # Mark as confirmed when written by discovery
                "search_publications": search_publications,
                "cpv_label": cpv_label,
                "publication_detail": publication_detail,
                "updated_at": updated_at,
            },
            f,
            indent=2,
        )
    logger.info("Discovered endpoints written to %s (confirmed=True)", cache_file)
    return discovered
