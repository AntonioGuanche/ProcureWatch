# PublicProcurement.be Integration

This document describes how to collect, import, and query procurement notices from publicprocurement.be.

## Overview

The integration supports two data sources behind a unified **connectors** layer:

1. **Official Belgian e-Procurement API** (OAuth2): For use when credentials are delivered; Media API / Partner API.
2. **Playwright fallback** (`scripts/collect_publicprocurement.js`): Uses a browser to intercept API responses from publicprocurement.be when the official API is not yet available.

Both expose the same interface and produce the same output shape. A single **ingestion** path imports collected JSON into the database; the existing importer (`ingest/import_publicprocurement.py`) is unchanged.

### Media API vs Partner API

- **Media API** (public): Search and read publication data; intended for broad use.
- **Partner API**: Extended access for accredited partners; may require different endpoints or scopes.

ProcureWatch is designed to use the **public Media API** first (OAuth2 client_credentials). Endpoints are **discovered automatically** from the published Swagger/OpenAPI specs (SEA and LOC) and cached in `data/_cache/eprocurement_endpoints.json` so they do not need to be configured by hand.

### OAuth2 Flow (Official API)

The official client uses the **client_credentials** grant:

1. **Token endpoint**: `POST https://public.int.fedservices.be/api/oauth2/token`
2. **Body**: `application/x-www-form-urlencoded` with `client_id`, `client_secret`, `grant_type=client_credentials`
3. **Response**: `access_token`, `expires_in`
4. **Usage**: Token is cached in memory and refreshed 60 seconds before expiry. All API requests use `Authorization: Bearer <token>`.

Credentials must be set in `.env` (`EPROC_CLIENT_ID`, `EPROC_CLIENT_SECRET`). On first use, the official client runs **endpoint discovery** (downloads `swagger.json` from SEA and LOC, finds search and CPV endpoints, writes the cache). If discovery fails (e.g. no network), run it manually (see below).

### Provider Modes (EPROC_MODE)

| Mode       | Behavior |
|-----------|----------|
| `official`  | Use only the official OAuth2 client. Fails if credentials are missing. |
| `playwright`| Use only the Playwright collector (Node.js script). |
| `auto` (default) | Use official if `EPROC_CLIENT_ID` and `EPROC_CLIENT_SECRET` are set; otherwise use Playwright. |

At runtime, the selected provider is logged (e.g. "e-Procurement provider: official (OAuth2)" or "e-Procurement provider: playwright (fallback)").

### TED (EU)

A second data source is **TED (Tenders Electronic Daily)** EU notices, using the official TED Search API (no scraping). The TED connector lives in `connectors/ted/` and follows the same architecture style as `connectors/eprocurement/`.

**Configuration (.env):**

| Variable | Default | Description |
|----------|---------|-------------|
| `TED_MODE` | `official` | `official` to use the TED Search API; `off` to disable. |
| `TED_SEARCH_BASE_URL` | `https://api.ted.europa.eu` | Base URL for the TED Search API (e.g. `POST /v3/notices/search`). Make it configurable; do not hardcode in code paths. |
| `TED_TIMEOUT_SECONDS` | `30` | HTTP timeout in seconds for TED requests. |

TED notices are stored with **source `ted.europa.eu`**, stable `source_id` (TED notice id), and `url` pointing to the TED notice page. No collisions with `publicprocurement.be` notices.

**Sync TED (CLI):**

```powershell
python ingest/sync_ted.py --term solar --page 1 --page-size 25
```

- **Arguments:** `--term`, `--page`, `--page-size`, `--out-dir` (default `data/raw/ted`), `--import` (default) / `--no-import`.
- Saves raw result to `data/raw/ted/ted_<timestamp>.json`. If `--import` is set, runs `python ingest/import_ted.py <raw_file_path>` as subprocess.
- Prints a JSON summary: `fetched`, `imported_new`, `imported_updated`, `errors`, `saved_path`.

**Import a raw TED file manually:**

```powershell
python ingest/import_ted.py data/raw/ted/ted_<timestamp>.json
```

**Offline tests (no network):**

```powershell
python -m pytest tests/test_import_ted.py tests/test_sync_ted.py tests/test_ted_official_client.py -v
```

All TED tests mock HTTP and subprocess; no real network calls.

## Prerequisites

- Node.js 18+ with npm
- Python 3.12+ with virtual environment activated
- Playwright browsers installed: `npx playwright install`

## Environment bootstrap (Windows)

On Windows, the project can suffer from **inconsistent Python environments** (multiple Python versions, missing modules like `requests`, pip not found, etc.). A bootstrap script ensures the **current** interpreter has all required dependencies without relying on bare `pip`.

**Why this exists:** Different terminals or IDEs may use different Python installations. Running the bootstrap with the same interpreter you use for scripts (e.g. `python scripts/discover_eprocurement_endpoints.py`) installs missing packages for that interpreter and avoids `ModuleNotFoundError`.

**Command to run:**

```powershell
python scripts/bootstrap_env.py
```

**Recommendation:** Run this once after cloning the repo, or whenever a `ModuleNotFoundError` appears (e.g. when running discovery or ingestion). The script only installs what is missing and prints clear status for each package.

The script also checks for a `.venv` at the repo root: if none exists, it prints a warning and how to create one; if one exists but you are not using it, it warns that another Python is in use. It does **not** auto-create or activate a venv (Python cannot do that reliably on Windows).

## Setup

### 1. Install Node.js Dependencies

```bash
npm install
```

Or if dependencies are already installed:

```bash
npm install playwright
```

### 2. Install Playwright Browsers

```bash
npx playwright install chromium
```

### 3. Run Database Migrations

```bash
python -m alembic upgrade head
```

This creates the necessary tables:
- `notices` (with new fields: `cpv_main_code`, `first_seen_at`, `last_seen_at`)
- `notice_cpv_additional` (for additional CPV codes)

## Confirmed working endpoint

The real search results endpoint is:

- **GET** `https://www.publicprocurement.be/api/sea/search/publications`  
  Query params: `terms`, `page`, `pageSize`.

The generateShortLink / byShortLink flow is unreliable and not used. Discovery and the official client are tuned so that **GET /search/publications** (query params) is the clear winner over `POST /search/publications/generateShortLink` and `GET /search/publications/byShortLink/{shortLink}`.

**Example curl** (with OAuth token):

```bash
curl -G "https://www.publicprocurement.be/api/sea/search/publications" \
  --data-urlencode "terms=travaux" \
  --data-urlencode "page=1" \
  --data-urlencode "pageSize=25" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python connector** (official client):

```python
from connectors.eprocurement.client import search_publications

result = search_publications(term="travaux", page=1, page_size=25)
# result = {"metadata": {"url": "...", "status": 200, "totalCount": ...}, "json": {...}}
```

## Endpoint discovery (official API)

Endpoints for the official API are discovered from the published Swagger/OpenAPI JSON:

- **SEA (Search)**: `https://public.int.fedservices.be/api/eProcurementSea/v1/doc/swagger.json`
- **LOC (Location/CPV)**: `https://public.int.fedservices.be/api/eProcurementLoc/v1/doc/swagger.json`

**Run discovery manually** (e.g. before first use or to refresh):

```powershell
python scripts/discover_eprocurement_endpoints.py
```

With `--force` to overwrite the cache:

```powershell
python scripts/discover_eprocurement_endpoints.py --force
```

The script downloads both swagger files, finds the best-matching endpoints for “search publications” and “CPV label”, prints the top 5 candidates and the selected one (with winner score and top reasons), and writes `data/_cache/eprocurement_endpoints.json`. Endpoints that clearly return a short link rather than publication results (e.g. paths containing `generateShortLink` or summaries containing "short link") are excluded from search selection. The official client then uses this cache for `search_publications` and `get_cpv_label`.

**Then run ingestion** with the official provider (after setting credentials in `.env`):

```powershell
python ingest/run_eprocurement_search.py travaux 1 25 --provider official
```

You can also force discovery from the ingest script:

```powershell
python ingest/run_eprocurement_search.py travaux 1 25 --discover
python ingest/run_eprocurement_search.py travaux 1 25 --force-discover
```

## Configuration (.env)

For **official API** (when credentials are available):

```env
EPROC_MODE=official
EPROC_OAUTH_TOKEN_URL=https://public.int.fedservices.be/api/oauth2/token
EPROC_CLIENT_ID=your_client_id
EPROC_CLIENT_SECRET=your_client_secret
EPROC_SEARCH_BASE_URL=https://public.int.fedservices.be/api/eProcurementSea/v1
EPROC_LOC_BASE_URL=https://public.int.fedservices.be/api/eProcurementLoc/v1
EPROC_TIMEOUT_SECONDS=30
```

For **Playwright fallback** (no credentials):

```env
EPROC_MODE=playwright
# or leave EPROC_MODE=auto and do not set EPROC_CLIENT_ID / EPROC_CLIENT_SECRET
```

## Usage

### End-to-end (Playwright collect + import latest)

1. Collect: open browser, type term, press Enter; script saves the first response that looks like search results.
2. Import the newest file into the database.

```powershell
node scripts/collect_publicprocurement.js travaux 1 25
python scripts/import_latest_publicprocurement.py
```

`import_latest_publicprocurement.py` finds the newest `data/raw/publicprocurement/publicprocurement_*.json` and runs the importer on it. Exits non-zero if no file is found.

### Step 1: Collect Data

**Option A – Unified Python script (recommended)**  
Uses the connectors layer (official API or Playwright depending on `EPROC_MODE`):

```bash
python ingest/run_eprocurement_search.py [term] [page] [page_size] [--provider official|playwright|auto]
```

**Example (auto mode):**
```bash
python ingest/run_eprocurement_search.py travaux 1 25
```

**Example (force Playwright):**
```bash
python ingest/run_eprocurement_search.py travaux 1 25 --provider playwright
```

Output is saved to `data/raw/publicprocurement/publicprocurement_<ISO>.json` (same naming as the Node collector).

**Option B – Node.js collector directly**

```bash
node scripts/collect_publicprocurement.js [term] [page] [pageSize]
```

**Parameters:**
- `term` (optional): Search term (default: "travaux")
- `page` (optional): Page number (default: 1)
- `pageSize` (optional): Results per page (default: 25)

**Example:**
```bash
node scripts/collect_publicprocurement.js travaux 1 25
```

**What happens:**
1. A browser window opens
2. You manually type the search term and press Enter
3. The script intercepts the API response (`POST /api/sea/search/publications`)
4. JSON is saved to `data/raw/publicprocurement/publicprocurement_<ISO_TIMESTAMP>.json`
5. Metadata (term, page, pageSize, timestamp) is included in the file

**Output:**
- Success: JSON file saved to `data/raw/publicprocurement/`
- Error (403/400): Debug info saved to `data/raw/publicprocurement/_debug/`

### Step 2: Import Data

Import the collected JSON file into the database:

```bash
python ingest/import_publicprocurement.py <json_file_path>
```

**Example:**
```bash
python ingest/import_publicprocurement.py data/raw/publicprocurement/publicprocurement_2026-01-28T20-49-47-147Z.json
```

**What happens:**
1. Reads the JSON file
2. Extracts publication data
3. Maps fields to database schema:
   - `external_id` ← `dossier.referenceNumber` or `dossier.number`
   - `title` ← `dossier.titles[]` (prefers FR, then EN)
   - `buyer_name` ← `buyer.name` (if available)
   - `cpv_main_code` ← `cpvMainCode.code`
   - `cpv_additional_codes[]` ← `cpvAdditionalCodes[].code`
   - `procedure_type` ← `dossier.procurementProcedureType`
   - `publication_date` ← `dispatchDate` or `insertionDate`
   - `deadline_date` ← `deadlineDate` (if available)
   - `url` ← constructed from `shortlink` or `noticeIds[0]`
   - `raw_json` ← full publication JSON
4. Inserts/updates notices in database
5. Handles deduplication by `(source, external_id)` unique constraint
6. Updates `last_seen_at` on conflict, sets `first_seen_at` on creation

**Output:**
- Progress: Shows each publication being processed
- Summary: Total created/updated counts

### Step 3: Enrich notices (optional)

Notices imported from search results may have missing `buyer_name` or `deadline_at`. The **enrichment script** uses the official API’s **publication detail** endpoint (discovered from SEA swagger) to fill these fields when possible. Enrichment is best-effort and non-blocking; only the **official** provider performs detail fetches.

**How to run enrichment:**

```powershell
python ingest/enrich_eprocurement_details.py [--since-days 2] [--limit 200] [--provider official|playwright|auto]
```

**Arguments:**
- `--since-days` (default: 2): Only consider notices seen in the last N days.
- `--limit` (default: 200): Max notices to process.
- `--provider`: `official` or `auto` (with credentials) to fetch detail; `playwright` skips enrichment.

**Requirements:**
- `EPROC_MODE=official` or `auto` with `EPROC_CLIENT_ID` and `EPROC_CLIENT_SECRET` set.
- Endpoint discovery must have run at least once (so `publication_detail` is in the cache). Run `python scripts/discover_eprocurement_endpoints.py --force` if needed.

**Example:**

```powershell
python scripts/discover_eprocurement_endpoints.py --force
python ingest/enrich_eprocurement_details.py --since-days 2 --limit 200
```

**Output:**
- `Enriched: N, Skipped/failed: M` — counts of notices updated vs. skipped (detail not found or provider not official).

### Step 3: Watchlist refresh and email notifications

**Daily refresh (CLI):** Run sync for all enabled watchlists (or one by `--watchlist-id`), with early-stop when two consecutive pages yield no new/updated imports. After refresh, if a watchlist has `notify_email` set and this is not the first run, an email digest of **new** notices (created since last refresh) is sent.

**How to run daily refresh:**

```powershell
python ingest/refresh_watchlists.py
```

**Options:**
- `--watchlist-id <uuid>` — refresh only this watchlist
- `--max-pages <int>` (default: 5) — max sync pages per watchlist
- `--page-size <int>` (default: 25) — page size for sync

**Example (one watchlist, 3 pages):**

```powershell
python ingest/refresh_watchlists.py --watchlist-id YOUR-WATCHLIST-UUID --max-pages 3
```

**Output:** JSON summary per watchlist: `watchlist_id`, `pages_fetched`, `fetched_total`, `imported_new_total`, `imported_updated_total`, `errors_total`.

**Manual refresh (API):** Trigger refresh for one watchlist. Rate limited: returns **429** if `last_refresh_at` is less than 10 minutes ago.

**Example (PowerShell, Invoke-RestMethod):**

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/watchlists/YOUR-WATCHLIST-ID/refresh"
```

**Email modes (config-driven):**

- **File mode (default, safe for dev):** Emails are written to disk instead of being sent. Set `EMAIL_MODE=file` (default) and optionally `EMAIL_OUTBOX_DIR` (default: `data/outbox`). Each email is a timestamped `.txt` file (e.g. `email_2026-01-28T22-00-00-000Z.txt`) containing headers (From, To, Subject) and plain-text body. Use this to verify digest content without sending real mail.
- **SMTP mode:** Set `EMAIL_MODE=smtp` and configure SMTP in `.env` (see below). Emails are sent via `smtplib` (TLS if enabled).

**Where to find outbox (file mode):**

- Default: `data/outbox` under the project root (or current working directory when the app/CLI runs).
- Override: set `EMAIL_OUTBOX_DIR` to an absolute or relative path (e.g. `C:\temp\procurewatch-outbox` or `./my-outbox`).

**SMTP env example (for production):**

```env
EMAIL_MODE=smtp
EMAIL_FROM=noreply@yourdomain.com
EMAIL_SMTP_HOST=smtp.example.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-user
EMAIL_SMTP_PASSWORD=your-password
EMAIL_SMTP_USE_TLS=true
```

**Notification rules:**
- Email is sent only if: `notify_email` is set on the watchlist, this is **not** the first run (`last_refresh_at` was already set), and there is at least one **new** notice (created since previous refresh).
- First run never sends (avoids spamming); `last_notified_at` is set anyway when `notify_email` is set.

### Step 4: Query via API

Start the FastAPI server:

```bash
python -m uvicorn app.main:app --reload
```

Then query the notices:

#### List Notices (Paginated)

**Watchlist CRUD and refresh:**
- `POST /api/watchlists` — create (body: name, is_enabled, term, cpv_prefix, buyer_contains, procedure_type, country, language, notify_email)
- `GET /api/watchlists?page=&page_size=` — list
- `GET /api/watchlists/{id}` — get one
- `PATCH /api/watchlists/{id}` — update (partial)
- `DELETE /api/watchlists/{id}` — delete
- `GET /api/watchlists/{id}/preview?page=&page_size=` — preview matching notices (NoticeListResponse shape)
- `POST /api/watchlists/{id}/refresh` — manual refresh (rate limited: 429 if last refresh < 10 min ago); returns JSON summary

#### List Notices (Paginated)

```bash
curl "http://localhost:8000/api/notices?page=1&page_size=25"
```

**Query Parameters:**
- `page` (default: 1): Page number
- `page_size` (default: 25, max: 100): Items per page
- `term` (optional): Search in title (case-insensitive)
- `cpv` (optional): Filter by CPV code (matches main or additional codes)
- `buyer` (optional): Filter by buyer name (case-insensitive)
- `deadline_from` (optional): ISO datetime, filter by deadline >= value
- `deadline_to` (optional): ISO datetime, filter by deadline <= value

**Examples:**
```bash
# Search for "construction" in title
curl "http://localhost:8000/api/notices?term=construction&page=1&page_size=10"

# Filter by CPV code
curl "http://localhost:8000/api/notices?cpv=45000000&page=1"

# Filter by buyer name
curl "http://localhost:8000/api/notices?buyer=municipality&page=1"

# Combined filters
curl "http://localhost:8000/api/notices?term=travaux&cpv=45&buyer=bruxelles&page=1&page_size=25"
```

**Response:**
```json
{
  "total": 150,
  "page": 1,
  "page_size": 25,
  "items": [
    {
      "id": "uuid",
      "source": "publicprocurement.be",
      "source_id": "PPP0T3-424/6018/RF/26/PO/1020",
      "title": "Travaux Klavertje 4",
      "buyer_name": "...",
      "country": "BE",
      "cpv_main_code": "45000000",
      "procedure_type": "OPEN",
      "published_at": "2026-01-28T00:00:00",
      "deadline_at": null,
      "url": "https://www.publicprocurement.be/bda/publication/...",
      "first_seen_at": "2026-01-28T20:50:00",
      "last_seen_at": "2026-01-28T20:50:00",
      "created_at": "2026-01-28T20:50:00",
      "updated_at": "2026-01-28T20:50:00"
    }
  ]
}
```

#### Get Single Notice

```bash
curl "http://localhost:8000/api/notices/{notice_id}"
```

**Example:**
```bash
curl "http://localhost:8000/api/notices/ced6f717-c602-4401-89dd-8094cdd164b2"
```

## Database Schema

### `notices` Table

- `id` (UUID, PK): Internal notice ID
- `source` (string): Source name ("publicprocurement.be")
- `source_id` (string): External ID from source (unique per source)
- `title` (string): Notice title
- `buyer_name` (string, nullable): Buyer organization name
- `country` (string, nullable): Country code (default: "BE")
- `cpv_main_code` (string, nullable): Main CPV code
- `cpv` (string, nullable): Main CPV code (backward compatibility)
- `procedure_type` (string, nullable): Procedure type (e.g., "OPEN", "NEG_WO_CALL_24")
- `published_at` (datetime, nullable): Publication date
- `deadline_at` (datetime, nullable): Deadline date
- `url` (string): Notice URL
- `raw_json` (TEXT, nullable): Full JSON from source
- `first_seen_at` (datetime): First time this notice was seen
- `last_seen_at` (datetime): Last time this notice was seen (updated on re-import)
- `created_at` (datetime): Record creation timestamp
- `updated_at` (datetime): Record update timestamp

**Indexes:**
- Unique: `(source, source_id)`
- Index: `published_at`, `deadline_at`, `cpv`, `cpv_main_code`

### `notice_cpv_additional` Table

- `id` (int, PK): Auto-increment ID
- `notice_id` (UUID, FK): Reference to `notices.id`
- `cpv_code` (string): Additional CPV code

**Index:**
- `notice_id` (for faster lookups)

### `watchlists` Table

- `id` (UUID, PK): Internal watchlist ID
- `name` (string): Display name
- `is_enabled` (boolean): Whether the watchlist is active
- `term` (string, nullable): Filter: case-insensitive contains on notice title
- `cpv_prefix` (string, nullable): Filter: main or additional CPV startswith prefix
- `buyer_contains` (string, nullable): Filter: case-insensitive contains on buyer_name (skips null buyer_name)
- `procedure_type` (string, nullable): Filter: exact match
- `country` (string, default "BE"): Filter: exact match
- `language` (string, nullable): Filter: exact match
- `notify_email` (string, nullable): Email address for digest; if null, no notification
- `last_refresh_at` (datetime, nullable): Last time this watchlist was refreshed
- `last_refresh_status` (string, nullable): JSON summary of last refresh
- `last_notified_at` (datetime, nullable): Last time an email digest was sent (or first run marked)
- `created_at` (datetime): Record creation timestamp
- `updated_at` (datetime): Record update timestamp

A notice matches a watchlist when it satisfies all non-null filters.

## Workflow Example

```powershell
# 1. Sync (search + save + import in one command)
python ingest/sync_eprocurement.py --term travaux --page 1 --page-size 25

# 2. Start API server
python -m uvicorn app.main:app --reload

# 3. Query notices
curl.exe "http://localhost:8000/api/notices?page=1&page_size=25"

# 4. Create a watchlist and preview matches
curl.exe -X POST "http://localhost:8000/api/watchlists" -H "Content-Type: application/json" -d "{\"name\": \"Travaux BE\", \"term\": \"travaux\", \"country\": \"BE\"}"
# Use the returned "id" in the next request:
curl.exe "http://localhost:8000/api/watchlists/{id}/preview?page=1&page_size=25"
```

## Troubleshooting

### Collector Issues

- **Timeout**: Make sure you type the search term and press Enter within 2 minutes
- **403/400 errors**: Check `data/raw/publicprocurement/_debug/` for error context
- **No response captured**: Verify the browser opened and you performed the search

### Import Issues

- **Integrity errors**: Usually means duplicate `(source, source_id)` - this is normal, the script updates existing records
- **Missing fields**: Some publications may not have all fields - the script handles nulls gracefully
- **JSON parsing errors**: Check that the JSON file is valid

### API Issues

- **Empty results**: Run migrations to ensure tables exist: `python -m alembic upgrade head`
- **Database errors**: Check that `DATABASE_URL` in `.env` points to a valid database

## Notes

- The collector uses Playwright to avoid WAF (Web Application Firewall) blocks
- No authentication tokens are hardcoded - they're obtained via browser navigation
- Data is deduplicated by `(source, source_id)` - re-importing updates `last_seen_at`
- CPV codes are normalized (dashes removed) for consistency
- The `raw_json` field stores the complete publication JSON for future reference
