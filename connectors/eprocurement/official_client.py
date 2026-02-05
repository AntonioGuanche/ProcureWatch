"""Official Belgian e-Procurement API client (OAuth2 client_credentials)."""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from connectors.eprocurement.openapi_discovery import (
    DiscoveredEndpoints,
    load_or_discover_endpoints,
)

logger = logging.getLogger(__name__)


class EProcurementCredentialsError(Exception):
    """Raised when OAuth credentials are missing or invalid."""

    pass


class EProcurementEndpointNotConfiguredError(NotImplementedError):
    """Raised when credentials are valid but endpoint mapping is not yet confirmed."""

    pass


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
        timeout_seconds: int = 30,
        endpoints: Optional[DiscoveredEndpoints] = None,
    ):
        self.token_url = token_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.search_base_url = (search_base_url or "").rstrip("/")
        self.loc_base_url = (loc_base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._endpoints: Optional[DiscoveredEndpoints] = endpoints

        # In-memory token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._refresh_before_seconds = 60

    def _get_endpoints(self) -> DiscoveredEndpoints:
        """Load or discover endpoints (lazy)."""
        if self._endpoints is not None:
            return self._endpoints
        try:
            self._endpoints = load_or_discover_endpoints(
                force=False,
                timeout=min(30, self.timeout_seconds),
            )
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
                "EPROC_CLIENT_ID and EPROC_CLIENT_SECRET must be set to use the official e-Procurement API. "
                "Set them in .env or use EPROC_MODE=playwright for the Playwright fallback."
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

    def _auth_headers(self) -> dict[str, str]:
        """Return headers with Bearer token."""
        token = self.get_access_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

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
        """Get CPV code label from Location API."""
        self._require_credentials()
        if not self.loc_base_url:
            raise EProcurementEndpointNotConfiguredError(
                "EPROC_LOC_BASE_URL is not set."
            )

        code_normalized = (code or "").strip().replace("-", "").replace(" ", "")
        if not code_normalized:
            return None

        endpoints = self._get_endpoints()
        cpv_ep = endpoints.cpv_label
        path = cpv_ep.get("path") or ""
        if not path:
            return None
        method = (cpv_ep.get("method") or "GET").upper()
        code_param = cpv_ep.get("code_param") or "code"
        lang_param = cpv_ep.get("lang_param") or "language"
        path_params = cpv_ep.get("path_params") or []

        # Substitute path params (e.g. /cpv/{code} -> /cpv/45000000)
        url_path = path
        code_in_path = False
        if path_params and "{" in path:
            for p in path_params:
                if p.lower() in ("code", "cpvcode", "cpv_code"):
                    url_path = url_path.replace("{" + p + "}", code_normalized)
                    code_in_path = True
                else:
                    url_path = url_path.replace("{" + p + "}", "")
            url_path = url_path.replace("{}", "").replace("//", "/")
        if not url_path.startswith("/"):
            url_path = "/" + url_path

        url = f"{self.loc_base_url.rstrip('/')}{url_path}"
        headers = self._auth_headers()

        params: dict[str, str] = {}
        if not code_in_path and code_param:
            params[code_param] = code_normalized
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
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError:
            return None
        except ValueError:
            return None

        # Extract label: common patterns
        # { "code": "...", "descriptions": [ { "language": "FR", "text": "..." } ] }
        # or list of such items
        lang_match = (lang or "fr").upper()[:2]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    label = _extract_label_from_cpv_item(item, lang_match)
                    if label:
                        return label
            return None
        return _extract_label_from_cpv_item(data, lang_match)


def _extract_label_from_cpv_item(item: dict[str, Any], lang_match: str) -> Optional[str]:
    """Extract human-readable label from a CPV item (code + descriptions)."""
    descriptions = item.get("descriptions") or item.get("description") or []
    if not isinstance(descriptions, list):
        descriptions = [descriptions] if descriptions else []
    for d in descriptions:
        if not isinstance(d, dict):
            continue
        lang = (d.get("language") or d.get("lang") or "").upper()[:2]
        text = d.get("text") or d.get("label") or d.get("description") or ""
        if lang == lang_match and text:
            return str(text).strip()
    # Fallback: first description in any language
    for d in descriptions:
        if isinstance(d, dict):
            text = d.get("text") or d.get("label") or d.get("description") or ""
            if text:
                return str(text).strip()
    return None
