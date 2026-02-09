"""Official TED (Tenders Electronic Daily) EU Search API client."""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# Retry: max attempts, backoff cap (seconds). Only 429/5xx are retried; 4xx (e.g. 400) are not.
TED_RETRY_ATTEMPTS = 3
TED_RETRY_BACKOFF_CAP = 10
RESPONSE_BODY_TRUNCATE = 4000
DEBUG_BODY_ON_ERROR_CHARS = 1000

# Confirmed working endpoint path
TED_SEARCH_PATH = "/v3/notices/search"

# Default fields for TED Search API (required, non-empty)
DEFAULT_FIELDS = [
    # Original 7 (confirmed working)
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "procedure-type",
    "main-classification-proc",
    # Additional confirmed from TED supported fields list
    "description-glo",
    "deadline-receipt-tender-date-lot",
    "place-of-performance-country-proc",
    "framework-estimated-value-glo",
    "contract-nature-main-proc",
]


def build_expert_query(term: str) -> str:
    """
    Build TED expert query from a simple search term.
    If term already looks like an expert query (contains operators), return unchanged.
    Otherwise, build OR expression across notice-title, description-glo, title-proc.
    """
    if not term or not isinstance(term, str):
        return '*'
    term = term.strip()
    if not term or term == '*':
        return '*'

    # Check if term already looks like an expert query
    expert_indicators = ['~', '!~', '=', '!=', ' OR ', ' AND ', ' NOT ', ' IN ']
    if any(indicator in term for indicator in expert_indicators):
        return term
    
    # Escape double quotes in term
    escaped_term = term.replace('"', '\\"')
    
    # Build OR expression across multiple fields
    return f'(notice-title ~ "{escaped_term}") OR (description-glo ~ "{escaped_term}") OR (title-proc ~ "{escaped_term}")'


class OfficialTEDClient:
    """
    Official TED Search API client.
    Uses confirmed endpoint: POST https://api.ted.europa.eu/v3/notices/search
    with expert query and required fields. Retry only 429/5xx.
    No authentication required (public API).
    """

    def __init__(
        self,
        search_base_url: str,
        timeout_seconds: int = 30,
    ):
        self.search_base_url = (search_base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Perform request with retry on 429 and 5xx; backoff capped."""
        last_exc: Exception | None = None
        resp: requests.Response | None = None
        for attempt in range(TED_RETRY_ATTEMPTS):
            try:
                resp = self._session.request(
                    method,
                    url,
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
                # Retry only 429 and 5xx; do not retry 4xx (e.g. 400 Bad Request)
                if resp.status_code in (429,) or (500 <= resp.status_code < 600):
                    if attempt < TED_RETRY_ATTEMPTS - 1:
                        backoff = min(2 ** attempt, TED_RETRY_BACKOFF_CAP)
                        logger.warning(
                            "TED API %s, retry in %ss (attempt %s/%s)",
                            resp.status_code,
                            backoff,
                            attempt + 1,
                            TED_RETRY_ATTEMPTS,
                        )
                        time.sleep(backoff)
                        continue
                    _raise_with_body(resp)
                return resp
            except requests.RequestException as e:
                last_exc = e
                if attempt < TED_RETRY_ATTEMPTS - 1:
                    backoff = min(2 ** attempt, TED_RETRY_BACKOFF_CAP)
                    logger.warning("TED request failed: %s, retry in %ss", e, backoff)
                    time.sleep(backoff)
        if last_exc:
            raise last_exc
        if resp is not None:
            return resp
        raise RuntimeError("TED request failed after retries")

    def search_notices(
        self,
        term: str,
        page: int = 1,
        page_size: int = 25,
        fields: Optional[list[str]] = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        """
        Search notices via POST https://api.ted.europa.eu/v3/notices/search.
        Uses expert query (built from term) and required fields array.
        Returns normalized shape: {"metadata": {...}, "json": <raw response>, "notices": [...]}.
        When debug=True, prints URL, request body, status, content-type, and on error first 1000 chars of body.
        """
        base_url = self.search_base_url.rstrip("/")
        url = f"{base_url}{TED_SEARCH_PATH}"

        expert_query = build_expert_query(term)
        fields_list = fields if fields and isinstance(fields, list) and len(fields) > 0 else DEFAULT_FIELDS
        limit_val = min(max(1, page_size), 250)

        body: dict[str, Any] = {
            "query": expert_query,
            "fields": fields_list,
            "page": page,
            "limit": limit_val,
            "scope": "ALL",
            "paginationMode": "PAGE_NUMBER",
        }

        resp = self._request_with_retry(
            "POST",
            url,
            json=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        status = resp.status_code
        if debug:
            _debug_print("POST", url, body, resp)

        # Detect HTML responses (wrong endpoint, e.g. website instead of API)
        ct = (resp.headers.get("Content-Type") or "")
        if isinstance(ct, str):
            ct = ct.lower()
        else:
            ct = ""
        resp_text = getattr(resp, "text", None)
        body_start = (resp_text[:50] if isinstance(resp_text, str) else "").strip()
        if "text/html" in ct or (body_start and body_start.lstrip().startswith("<")):
            snippet = (resp_text if isinstance(resp_text, str) else "")[:DEBUG_BODY_ON_ERROR_CHARS]
            raise ValueError(
                "Received HTML, likely wrong endpoint. Ensure TED_SEARCH_BASE_URL points to the API host "
                f"(e.g. https://api.ted.europa.eu) and run with --discover. Response snippet: {snippet!r}"
            )

        if not resp.ok:
            _raise_with_body(resp)

        try:
            data = resp.json()
        except ValueError:
            raise ValueError(
                f"TED Search API returned non-JSON (status={status}): {resp_text[:RESPONSE_BODY_TRUNCATE] if isinstance(resp_text, str) else ''}"
            ) from None

        # Parse response: notices array and totalCount
        notices = data.get("notices", []) if isinstance(data, dict) else []
        total_count = None
        if isinstance(data, dict):
            total_count = data.get("totalCount")
            if total_count is None:
                total_count = data.get("total")
            if total_count is None:
                total_count = data.get("totalResults")

        metadata = {
            "term": term,
            "page": page,
            "pageSize": page_size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": resp.url,
            "status": status,
            "totalCount": total_count,
        }
        return {"metadata": metadata, "json": data, "notices": notices}


def _raise_with_body(resp: requests.Response) -> None:
    """Raise HTTPError with response body (truncated) in the exception message."""
    resp_text = getattr(resp, "text", None)
    body_snippet = (resp_text if isinstance(resp_text, str) else "")[:RESPONSE_BODY_TRUNCATE]
    msg = f"{resp.status_code} Client Error: {resp.reason or 'Error'} for url: {resp.url}. Response body: {body_snippet}"
    raise requests.HTTPError(msg, request=resp.request, response=resp)


def _debug_print(method: str, url: str, body: Any, resp: requests.Response) -> None:
    """Print debug info: final URL, method, request body, status, content-type, and on error first 1000 chars of body."""
    final_url = getattr(resp, "url", url)
    print(f"[TED debug] final URL: {final_url}", flush=True)
    print(f"[TED debug] request method: {method}", flush=True)
    print(f"[TED debug] request params/body: {body}", flush=True)
    print(f"[TED debug] response status code: {resp.status_code}", flush=True)
    ct = resp.headers.get("Content-Type", "")
    print(f"[TED debug] response content-type: {ct}", flush=True)
    if resp.status_code < 200 or resp.status_code >= 300:
        resp_text = getattr(resp, "text", None)
        body_preview = (resp_text if isinstance(resp_text, str) else "")[:DEBUG_BODY_ON_ERROR_CHARS]
        print(f"[TED debug] response body (first {DEBUG_BODY_ON_ERROR_CHARS} chars): {body_preview}", flush=True)
