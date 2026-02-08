"""Official Belgian e-Procurement API client (OAuth2 client_credentials)."""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from app.connectors.bosa.exceptions import (
    EProcurementCredentialsError,
    EProcurementEndpointNotConfiguredError,
)
from app.connectors.bosa.openapi_discovery import (
    DiscoveredEndpoints,
    cache_path,
    load_or_discover_endpoints,
)

logger = logging.getLogger(__name__)


class OfficialEProcurementClient:
    """
    Official Belgian e-Procurement API client.
    Uses OAuth2 client_credentials flow. Token is cached and refreshed before expiry.
    Endpoints are loaded from cache or discovered from Swagger/OpenAPI.
    """

    def __init__(
        self,
        token_url: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        search_base_url: Optional[str] = None,
        loc_base_url: Optional[str] = None,
        dos_base_url: Optional[str] = None,
        timeout_seconds: int = 30,
        endpoints: Optional[DiscoveredEndpoints] = None,
        endpoint_confirmed: bool = False,
        cpv_probe: bool = False,
    ):
        self.token_url = token_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.search_base_url = (search_base_url or "").rstrip("/")
        self.loc_base_url = (loc_base_url or "").rstrip("/")
        self.dos_base_url = (dos_base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cpv_probe = cpv_probe
        self._endpoints: Optional[DiscoveredEndpoints] = endpoints
        # If endpoints are provided, consider them confirmed (no need for explicit flag)
        self._endpoint_confirmed = endpoint_confirmed or (endpoints is not None)

        # In-memory token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._refresh_before_seconds = 60

    @staticmethod
    def _truthy(value: Any) -> bool:
        """Check if value is truthy (handles strings like 'true', '1', etc.)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    @staticmethod
    def _endpoints_confirmed_from_cache() -> bool:
        """Check if endpoints cache exists and is confirmed."""
        try:
            cache_file = cache_path()
            if not cache_file.exists():
                return False
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("confirmed", False)
        except Exception:
            return False

    @staticmethod
    def _endpoints_confirmed_from_env() -> bool:
        """Check if endpoints are confirmed via environment variable."""
        env_flag = os.environ.get("EPROCUREMENT_ENDPOINT_CONFIRMED", "").strip()
        return OfficialEProcurementClient._truthy(env_flag)

    def _ensure_endpoints_confirmed(self) -> None:
        """
        Ensure endpoints are confirmed before making API calls.
        Checks: env var EPROCUREMENT_ENDPOINT_CONFIRMED OR confirmed cache.
        Raises EProcurementEndpointNotConfiguredError if not confirmed.
        """
        # If endpoints were provided via constructor, consider them confirmed
        if self._endpoint_confirmed or self._endpoints is not None:
            return
        
        # Check env var
        if self._endpoints_confirmed_from_env():
            self._endpoint_confirmed = True
            return
        
        # Check cache
        if self._endpoints_confirmed_from_cache():
            self._endpoint_confirmed = True
            return
        
        # Not confirmed - raise error BEFORE any network calls
        cache_file = cache_path()
        raise EProcurementEndpointNotConfiguredError(
            f"Endpoints are not confirmed. "
            f"Run: python scripts/discover_eprocurement_endpoints.py --confirm\n"
            f"Cache file: {cache_file}"
        )

    def _get_endpoints(self) -> DiscoveredEndpoints:
        """Load or discover endpoints (lazy)."""
        if self._endpoints is not None:
            return self._endpoints
        try:
            self._endpoints = load_or_discover_endpoints(
                force=False,
                timeout=min(30, self.timeout_seconds),
            )
            # If endpoints were loaded from confirmed cache, mark as confirmed
            if self._endpoints is not None and self._endpoints_confirmed_from_cache():
                self._endpoint_confirmed = True
            return self._endpoints
        except Exception as e:
            logger.warning("Endpoint discovery failed: %s", e)
            raise EProcurementEndpointNotConfiguredError(
                f"Could not load or discover endpoints: {e}. "
                "Run: python scripts/discover_eprocurement_endpoints.py"
            ) from e

    def _require_credentials(self) -> None:
        """Raise clear exception if credentials are missing."""
        if not self.client_id or not self.client_secret:
            raise EProcurementCredentialsError(
                "OAuth credentials are missing. Set EPROC_CLIENT_ID/EPROC_CLIENT_SECRET (legacy) "
                "or EPROCUREMENT_{INT,PR}_CLIENT_ID/EPROCUREMENT_{INT,PR}_CLIENT_SECRET in .env. "
                "Or use EPROC_MODE=playwright for the Playwright fallback."
            )

    def get_access_token(self) -> str:
        """
        Get a valid access token. Caches in memory and refreshes 60 seconds before expiry.
        """
        self._require_credentials()

        now = time.time()
        if self._access_token and self._token_expires_at > (now + self._refresh_before_seconds):
            return self._access_token

        response = requests.post(
            self.token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)

        if not access_token:
            raise EProcurementCredentialsError(
                "OAuth token response did not contain access_token."
            )

        self._access_token = access_token
        self._token_expires_at = now + expires_in
        logger.info("Obtained new OAuth access token (expires in %s seconds)", expires_in)
        return self._access_token

    @staticmethod
    def _make_trace_id() -> str:
        """Generate a UUID v4 trace ID for BelGov-Trace-Id header."""
        return str(uuid.uuid4())

    def _auth_headers(self, extra_headers: Optional[dict[str, str]] = None, accept_language: Optional[str] = None) -> dict[str, str]:
        """
        Return headers for authenticated e-Procurement API calls.
        Includes Authorization, Accept, BelGov-Trace-Id (required by BOSA API), and Accept-Language.
        
        Args:
            extra_headers: Optional dict of additional headers to merge on top.
            accept_language: Optional language code (e.g., "fr", "nl"). Defaults to "fr".
        
        Returns:
            Dict with Authorization, Accept, BelGov-Trace-Id, Accept-Language, and any extra headers.
        """
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "BelGov-Trace-Id": self._make_trace_id(),
            "Accept-Language": accept_language or "fr",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """
        Make an authenticated HTTP request with Bearer token.
        Adds Authorization header and Accept: application/json.
        Does NOT log secrets or token.
        """
        self._require_credentials()
        auth_headers = self._auth_headers()
        if headers:
            auth_headers.update(headers)
        timeout = timeout or self.timeout_seconds
        return requests.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_data,
            headers=auth_headers,
            timeout=timeout,
        )

    def discover_openapi(self, swagger_url: str, cache_dir: Optional[Path] = None) -> dict[str, Any]:
        """
        Download and cache OpenAPI/Swagger JSON from URL.
        Caches to .cache/eprocurement/{env}/sea_swagger.json (or custom cache_dir).
        Returns parsed swagger dict.
        """
        if cache_dir is None:
            cache_dir = Path(".cache/eprocurement")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "sea_swagger.json"

        # Try to load from cache first
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    logger.debug("Loaded swagger from cache: %s", cache_file)
                    return cached
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load cached swagger: %s", e)

        # Download swagger JSON
        try:
            response = requests.get(swagger_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            swagger_data = response.json()
        except requests.RequestException as e:
            logger.error("Failed to download swagger from %s: %s", swagger_url, e)
            raise
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in swagger response: %s", e)
            raise ValueError(f"Invalid JSON in swagger response: {e}") from e

        # Cache the swagger data
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(swagger_data, f, indent=2)
            logger.debug("Cached swagger to: %s", cache_file)
        except IOError as e:
            logger.warning("Failed to cache swagger: %s", e)

        return swagger_data

    def search_publications(
        self,
        term: str,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        """
        Search publications. Returns structure compatible with Playwright collector:
        {"metadata": {...}, "json": {...}}
        """
        self._require_credentials()
        if not self.search_base_url:
            raise EProcurementEndpointNotConfiguredError(
                "EPROC_SEARCH_BASE_URL is not set."
            )

        # Guard: ensure endpoints are confirmed BEFORE any network call
        self._ensure_endpoints_confirmed()

        endpoints = self._get_endpoints()
        search_ep = endpoints.search_publications
        path = search_ep.get("path") or ""
        if not path:
            raise EProcurementEndpointNotConfiguredError(
                "No search_publications endpoint discovered. Run: python scripts/discover_eprocurement_endpoints.py"
            )
        method = (search_ep.get("method") or "POST").upper()
        style = search_ep.get("style") or "json_body"
        term_param = search_ep.get("term_param") or "terms"
        page_param = search_ep.get("page_param") or "page"
        page_size_param = search_ep.get("page_size_param") or "pageSize"

        base_url = self.search_base_url.rstrip("/")
        url = f"{base_url}{path}"

        # GET /search/publications: query params only, no JSON body
        qparams = {
            term_param: term,
            page_param: page,
            page_size_param: page_size,
        }
        headers = self._auth_headers()
        try:
            if method == "GET":
                resp = requests.request(
                    method,
                    url,
                    params=qparams,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            elif style == "json_body":
                resp = requests.request(
                    method,
                    url,
                    json=qparams,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                resp = requests.request(
                    method,
                    url,
                    params=qparams,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            status = resp.status_code
            resp.raise_for_status()

            try:
                data = resp.json()
            except ValueError:
                raise ValueError(
                    f"Search API returned non-JSON (status={status}): {resp.text[:300]}"
                )

            total_count = data.get("totalCount") if isinstance(data, dict) else None
            # metadata.url = exact full URL used (base + path + query, no secrets)
            metadata = {
                "term": term,
                "page": page,
                "pageSize": page_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": resp.url,
                "status": status,
                "totalCount": total_count,
            }
            return {"metadata": metadata, "json": data}

        except requests.HTTPError as e:
            raise ValueError(
                f"Search API error (status={e.response.status_code}): {e.response.text[:300]}"
            ) from e

    def get_publication_workspace(self, publication_workspace_id: str) -> Optional[dict[str, Any]]:
        """
        Get publication workspace from Dos API.
        
        Args:
            publication_workspace_id: The publication workspace identifier.
        
        Returns:
            JSON dict if successful, None on 401/403/404.
        
        Raises:
            EProcurementEndpointNotConfiguredError: If dos_base_url is not set.
        """
        if not self.dos_base_url:
            raise EProcurementEndpointNotConfiguredError(
                "EPROC_DOS_BASE_URL is not set."
            )
        
        self._require_credentials()
        self._ensure_endpoints_confirmed()
        
        url = f"{self.dos_base_url.rstrip('/')}/publication-workspaces/{publication_workspace_id}"
        headers = self._auth_headers()
        
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code in (401, 403, 404):
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError:
            return None
        except ValueError:
            return None

    def get_notice(self, notice_id: str) -> Optional[dict[str, Any]]:
        """
        Get notice from Dos API.
        
        Args:
            notice_id: The notice identifier.
        
        Returns:
            JSON dict if successful, None on 401/403/404.
        
        Raises:
            EProcurementEndpointNotConfiguredError: If dos_base_url is not set.
        """
        if not self.dos_base_url:
            raise EProcurementEndpointNotConfiguredError(
                "EPROC_DOS_BASE_URL is not set."
            )
        
        self._require_credentials()
        self._ensure_endpoints_confirmed()
        
        url = f"{self.dos_base_url.rstrip('/')}/notices/{notice_id}"
        headers = self._auth_headers()
        
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code in (401, 403, 404):
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError:
            return None
        except ValueError:
            return None

    def get_publication_detail(self, publication_id: str) -> Optional[dict[str, Any]]:
        """
        Get a single publication by ID using the discovered publication_detail endpoint.
        Returns parsed JSON or None on 401/403/404 or if endpoint is not configured.
        """
        if not publication_id or not str(publication_id).strip():
            return None
        try:
            self._require_credentials()
        except EProcurementCredentialsError:
            return None
        if not self.search_base_url:
            return None
        try:
            endpoints = self._get_endpoints()
        except EProcurementEndpointNotConfiguredError:
            return None
        detail_ep = endpoints.publication_detail
        path = (detail_ep or {}).get("path") or ""
        if not path or not (detail_ep or {}).get("id_param"):
            return None
        id_param = (detail_ep or {}).get("id_param", "id")
        url_path = path.replace("{" + id_param + "}", str(publication_id).strip())
        for p in (detail_ep or {}).get("path_params") or []:
            if "{" + p + "}" in url_path and p != id_param:
                url_path = url_path.replace("{" + p + "}", "")
        url_path = url_path.replace("{}", "").replace("//", "/")
        if not url_path.startswith("/"):
            url_path = "/" + url_path
        url = f"{self.search_base_url.rstrip('/')}{url_path}"
        headers = self._auth_headers()
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code in (401, 403, 404):
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError:
            return None
        except ValueError:
            return None

    def get_cpv_label(self, code: str, lang: str = "fr") -> Optional[str]:
        """
        Get CPV code label from Location API.
        
        Returns:
            Label string if found, None otherwise.
        """
        label, _, _, _, _, _, _ = self.get_cpv_label_with_response(code=code, lang=lang)
        return label

    def _generate_cpv_candidate_ids(self, code: str) -> list[str]:
        """
        Generate candidate CPV IDs to try in order.
        
        Args:
            code: Input CPV code (e.g., "45000000-7" or "45000000")
        
        Returns:
            List of candidate IDs to try:
            1. Raw input trimmed (keep dash/check digit if present), e.g. "45000000-7"
            2. Digits-only 8-digit base code, e.g. "45000000"
            3. Digits-only full (remove dash only), e.g. "450000007"
        """
        if not code:
            return []
        
        code_trimmed = code.strip()
        candidates = []
        
        # Candidate 1: Raw input trimmed (keep dash/check digit if present)
        if code_trimmed:
            candidates.append(code_trimmed)
        
        # Candidate 2: Digits-only 8-digit base code (remove dash and everything after)
        code_base = code_trimmed.split("-")[0] if "-" in code_trimmed else code_trimmed
        code_digits_only = "".join(c for c in code_base if c.isdigit())
        if code_digits_only and code_digits_only != code_trimmed:
            # Ensure it's at least 8 digits, pad if needed (unlikely but safe)
            if len(code_digits_only) >= 8:
                candidates.append(code_digits_only[:8])
            elif code_digits_only:
                candidates.append(code_digits_only)
        
        # Candidate 3: Digits-only full (remove dash only, keep all digits)
        code_no_dash = "".join(c for c in code_trimmed if c.isdigit() or c == "-")
        code_no_dash = code_no_dash.replace("-", "")
        if code_no_dash and code_no_dash != code_trimmed and code_no_dash not in candidates:
            candidates.append(code_no_dash)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)
        
        return unique_candidates

    def get_cpv_label_with_response(self, code: str, lang: str = "fr") -> tuple[Optional[str], Optional[dict[str, Any]], Optional[int], Optional[str], Optional[str], Optional[list[str]], Optional[str]]:
        """
        Get CPV code label from Location API with full response data.
        
        Returns:
            Tuple of (label, response_json, status_code, raw_text_preview, label_source, tried_ids, last_url).
            - label: Extracted label string or None
            - response_json: Parsed JSON dict/list or None if not JSON
            - status_code: HTTP status code (always present, even on errors)
            - raw_text_preview: First 500 chars of response body if not JSON (for diagnostics)
            - label_source: "api" | "local" | "none"
            - tried_ids: List of candidate IDs that were tried (for diagnostics)
            - last_url: Last URL that was tried (for diagnostics)
            
        Always returns a tuple, even on HTTP errors, to enable diagnostics.
        Tries multiple candidate IDs in order until a 200 response with label is found.
        """
        self._require_credentials()
        if not self.loc_base_url:
            raise EProcurementEndpointNotConfiguredError(
                "EPROC_LOC_BASE_URL is not set."
            )
        
        # Guard: ensure endpoints are confirmed BEFORE any network call
        self._ensure_endpoints_confirmed()

        # Generate candidate IDs to try
        candidate_ids = self._generate_cpv_candidate_ids(code)
        if not candidate_ids:
            return (None, None, None, None, "none", [], None)

        endpoints = self._get_endpoints()
        cpv_ep = endpoints.cpv_label
        path = cpv_ep.get("path") or ""
        if not path:
            return (None, None, None, None, "none", candidate_ids, None)
        method = (cpv_ep.get("method") or "GET").upper()
        code_param = cpv_ep.get("code_param") or "code"
        lang_param = cpv_ep.get("lang_param") or "language"
        path_params = cpv_ep.get("path_params") or []

        # Try each candidate ID in order until we get a 200 with label
        lang_match = (lang or "fr").upper()[:2]
        last_status_code = None
        last_response_json = None
        last_raw_text_preview = None
        last_url = None
        
        for candidate_id in candidate_ids:
            # Generic path param substitution
            url_path = path
            code_in_path = False
            param_to_substitute = None
            
            if path_params and "{" in path:
                # Check if code_param matches any path param
                for p in path_params:
                    if p.lower() == code_param.lower():
                        param_to_substitute = p
                        code_in_path = True
                        break
                
                # If no match and exactly one path param, use it
                if not param_to_substitute and len(path_params) == 1:
                    param_to_substitute = path_params[0]
                    code_in_path = True
                
                # Fallback: try common code-related names
                if not param_to_substitute:
                    for p in path_params:
                        if p.lower() in ("code", "cpvcode", "cpv_code", "id"):
                            param_to_substitute = p
                            code_in_path = True
                            break
                
                # Substitute the identified param with current candidate ID
                if param_to_substitute:
                    url_path = url_path.replace("{" + param_to_substitute + "}", candidate_id)
                
                # Remove any remaining path params (empty substitution)
                for p in path_params:
                    if p != param_to_substitute and "{" + p + "}" in url_path:
                        url_path = url_path.replace("{" + p + "}", "")
                
                url_path = url_path.replace("{}", "").replace("//", "/")
            
            if not url_path.startswith("/"):
                url_path = "/" + url_path

            url = f"{self.loc_base_url.rstrip('/')}{url_path}"
            last_url = url
            # Include Accept-Language header based on lang parameter
            headers = self._auth_headers(accept_language=lang)

            params: dict[str, str] = {}
            if not code_in_path and code_param:
                params[code_param] = candidate_id
            if lang_param:
                params[lang_param] = (lang or "fr").upper()[:2]

            try:
                resp = requests.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                status_code = resp.status_code
                last_status_code = status_code
                
                # Handle 204 No Content - continue to next candidate
                if status_code == 204:
                    continue
                
                # Try to parse JSON
                response_json = None
                raw_text_preview = None
                try:
                    response_json = resp.json()
                    last_response_json = response_json
                except (ValueError, json.JSONDecodeError):
                    # Not JSON - store text preview
                    text_content = resp.text
                    raw_text_preview = text_content[:500] if text_content else None
                    last_raw_text_preview = raw_text_preview
                    # Continue to next candidate if not JSON
                    continue
                
                # Raise for status if not 2xx (204 already handled above)
                resp.raise_for_status()
                
                # Extract label from successful response
                label = None
                if isinstance(response_json, list):
                    for item in response_json:
                        if isinstance(item, dict):
                            label = _extract_label_from_cpv_item(item, lang_match)
                            if label:
                                break
                elif isinstance(response_json, dict):
                    label = _extract_label_from_cpv_item(response_json, lang_match)
                
                # If we got a 200 with a label, return it
                if label:
                    return (label, response_json, status_code, raw_text_preview, "api", candidate_ids, url)
                
                # If 200 but no label, try local fallback
                local_label = self._get_local_cpv_label(candidate_id, lang)
                if local_label:
                    return (local_label, response_json, status_code, raw_text_preview, "local", candidate_ids, url)
                
                # 200 but no label found - continue to next candidate
                continue
                
            except requests.HTTPError as e:
                # HTTP error - continue to next candidate
                status_code = e.response.status_code if hasattr(e, 'response') and e.response else 0
                last_status_code = status_code
                
                if hasattr(e, 'response') and e.response:
                    try:
                        last_response_json = e.response.json()
                    except (ValueError, json.JSONDecodeError):
                        text_content = e.response.text
                        last_raw_text_preview = text_content[:500] if text_content else None
                
                # Continue to next candidate
                continue
                
            except (requests.RequestException, ValueError):
                # Network error - continue to next candidate
                continue
        
        # All candidates tried, none returned a label
        # Try local fallback with first candidate (8-digit base)
        if candidate_ids:
            base_candidate = candidate_ids[0].split("-")[0] if "-" in candidate_ids[0] else candidate_ids[0]
            base_candidate = "".join(c for c in base_candidate if c.isdigit())[:8]
            if base_candidate:
                local_label = self._get_local_cpv_label(base_candidate, lang)
                if local_label:
                    return (local_label, None, last_status_code or 204, None, "local", candidate_ids, last_url)
        
        # No label found - return diagnostics
        return (None, last_response_json, last_status_code or 204, last_raw_text_preview, "none", candidate_ids, last_url)

    def _probe_cpv_label(self, code: str, lang: str = "fr") -> Optional[str]:
        """
        Probe CPV label using different query parameter strategies.
        
        Tries multiple query param candidates to find the CPV label when
        the path-based endpoint returns 204/404.
        
        Args:
            code: Normalized CPV code (8 digits, no check digit)
            lang: Language code (default: "fr")
        
        Returns:
            Label string if found, None otherwise.
        """
        if not self.loc_base_url:
            return None
        
        # Probe candidates: different query param names
        probe_candidates = [
            {"id": code},
            {"code": code},
            {"cpv": code},
            {"search": code},
            {"terms": code},
        ]
        
        lang_match = (lang or "fr").upper()[:2]
        headers = self._auth_headers(accept_language=lang)
        
        for params in probe_candidates:
            try:
                # Try GET /cpvs with query params
                url = f"{self.loc_base_url.rstrip('/')}/cpvs"
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # Check if response contains the target code
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    item_code = str(item.get("code", "")).replace("-", "").replace(" ", "")
                                    if item_code == code:
                                        label = _extract_label_from_cpv_item(item, lang_match)
                                        if label:
                                            return label
                        elif isinstance(data, dict):
                            item_code = str(data.get("code", "")).replace("-", "").replace(" ", "")
                            if item_code == code:
                                label = _extract_label_from_cpv_item(data, lang_match)
                                if label:
                                    return label
                    except (ValueError, json.JSONDecodeError):
                        continue
            except requests.RequestException:
                # Continue to next candidate
                continue
        
        return None

    def _get_local_cpv_label(self, code: str, lang: str = "fr") -> Optional[str]:
        """
        Get CPV label from local fallback file.
        
        Args:
            code: Normalized CPV code (8 digits, no check digit)
            lang: Language code (default: "fr")
        
        Returns:
            Label string if found in local file, None otherwise.
        """
        if lang.lower() != "fr":
            # Only French labels supported for now
            return None
        
        try:
            cpv_file = Path("data") / "cpv" / "cpv_labels_fr.json"
            if not cpv_file.exists():
                return None
            
            with open(cpv_file, "r", encoding="utf-8") as f:
                cpv_map = json.load(f)
            
            if not isinstance(cpv_map, dict):
                return None
            
            return cpv_map.get(code)
        except (IOError, json.JSONDecodeError, KeyError):
            # Silently fail - local fallback is optional
            return None


def _extract_label_from_cpv_item(item: dict[str, Any], lang_match: str) -> Optional[str]:
    """
    Extract human-readable label from a CPV item.
    
    Supports multiple response shapes:
    - Direct string fields: label, name, text, description, descriptionFR, descriptionNL
    - Nested descriptions/translations arrays
    - Translations dicts with language/text pairs
    """
    if not isinstance(item, dict):
        return None
    
    # Try direct string fields first (language-specific)
    if lang_match == "FR":
        for key in ("descriptionFR", "labelFR", "nameFR", "textFR"):
            value = item.get(key)
            if value and isinstance(value, str):
                return value.strip()
    elif lang_match == "NL":
        for key in ("descriptionNL", "labelNL", "nameNL", "textNL"):
            value = item.get(key)
            if value and isinstance(value, str):
                return value.strip()
    
    # Try generic direct fields
    for key in ("label", "name", "text", "description"):
        value = item.get(key)
        if value and isinstance(value, str):
            return value.strip()
    
    # Try descriptions array (existing logic)
    descriptions = item.get("descriptions") or item.get("description") or []
    if not isinstance(descriptions, list):
        descriptions = [descriptions] if descriptions else []
    
    # Try translations array/dict
    translations = item.get("translations") or item.get("translation") or []
    if not isinstance(translations, list):
        translations = [translations] if translations else []
    
    # Combine descriptions and translations for processing
    all_items = descriptions + translations
    
    # Look for language match in descriptions/translations
    for d in all_items:
        if not isinstance(d, dict):
            continue
        lang = (d.get("language") or d.get("lang") or "").upper()[:2]
        text = d.get("text") or d.get("label") or d.get("description") or d.get("name") or ""
        if lang == lang_match and text:
            return str(text).strip()
    
    # Fallback: first description/translation in any language
    for d in all_items:
        if isinstance(d, dict):
            text = d.get("text") or d.get("label") or d.get("description") or d.get("name") or ""
            if text:
                return str(text).strip()
    
    return None
