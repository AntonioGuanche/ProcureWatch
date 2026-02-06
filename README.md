# ProcureWatch API

Production-ready FastAPI backend for ProcureWatch, a platform that monitors public procurement opportunities and alerts users about relevant calls for tenders.

## Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL (Neon, requires SSL)
- SQLAlchemy 2.0
- Alembic migrations
- Pydantic v2 + pydantic-settings
- Uvicorn

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL database (Neon recommended)

### Setup

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```

2. **Activate virtual environment:**
   ```bash
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables:**
   
   Create a `.env` file (copy from `.env.example` if needed):
   ```powershell
   Copy-Item .env.example .env
   ```
   
   The `.env` file is required for local development. Edit `.env` and set your `DATABASE_URL`:
   
   **For local development (recommended - single SQLite database):**
   ```powershell
   $env:DATABASE_URL="sqlite:///./dev.db"
   ```
   Or add to `.env`:
   ```
   DATABASE_URL=sqlite+pysqlite:///./dev.db
   ```
   **Windows-safe absolute path:** If you need an absolute path (e.g. for scripts), use:
   ```powershell
   # Example: resolve to absolute path so all tools use the same file
   $env:DATABASE_URL="sqlite:///C:/Users/YourName/ProcureWatch/dev.db"
   ```
   The app resolves `sqlite:///./dev.db` to an absolute path internally, so relative URLs are fine. This creates a persistent `dev.db` file in the project root. **All components (FastAPI app, TED/BOSA ingest, watchlists) use the same database.** Your data will persist between server restarts.
   
   **For quick tests (ephemeral):**
   ```
   DATABASE_URL=sqlite+pysqlite:///:memory:
   ```
   This uses an in-memory database that is cleared when the server stops. Useful for quick tests but not recommended for regular development.
   
   **For production (Neon PostgreSQL):**
   ```
   DATABASE_URL=postgresql+psycopg://user:password@host.neon.tech/dbname?sslmode=require
   ```
   
   **Important:** If you switch between database URLs (e.g., from `:memory:` to `./dev.db`), you must re-run migrations:
   ```powershell
   python -m alembic upgrade head
   ```

5. **Run database migrations (required once):**
   ```powershell
   python -m alembic upgrade head
   ```
   This creates all tables in `dev.db`. Run migrations after:
   - First-time setup
   - Switching database URLs
   - Pulling new migrations from the repository

6. **Start the development server:**
   ```powershell
   python -m uvicorn app.main:app --reload
   ```
   
   To stop the server, press `CTRL+C`.
   
   **After switching database URLs:**
   - Stop the server (`CTRL+C`)
   - Run migrations: `python -m alembic upgrade head`
   - Restart the server: `python -m uvicorn app.main:app --reload`

7. **Verify the API is running:**
   - Root: http://localhost:8000/
   - Health: http://localhost:8000/health
   - Docs: http://localhost:8000/docs

## Running Tests

```powershell
python -m pytest -q
```

## Database Migrations

**Important:** All components (FastAPI app, TED ingest, watchlists) use the same database: `dev.db` by default.

### Apply migrations (required once):
```powershell
python -m alembic upgrade head
```
This creates all tables in `dev.db`. Run this after:
- First-time setup
- Pulling new migrations from the repository

### Create a new migration:
```powershell
python -m alembic revision --autogenerate -m "description"
```

### Rollback last migration:
```powershell
python -m alembic downgrade -1
```

## TED Data Ingestion

Import TED (Tenders Electronic Daily) EU notices into `dev.db`:

```powershell
# Set database URL (if not in .env)
$env:DATABASE_URL="sqlite:///./dev.db"

# Run migrations first (if needed)
python -m alembic upgrade head

# Fetch and import TED notices
python scripts/sync_ted.py --query "forest restoration" --limit 25 --import
```

**Note:** The `--import` flag automatically runs migrations if needed. The importer uses `dev.db` by default (or `DATABASE_URL` if set).

## BOSA Data Ingestion

Import BOSA e-Procurement (Belgian) notices into the same `dev.db`:

```powershell
# Set database URL (if not in .env)
$env:DATABASE_URL="sqlite:///./dev.db"

# Run migrations first (if needed)
python -m alembic upgrade head

# Fetch and import BOSA notices (requires EPROC_CLIENT_ID / EPROC_CLIENT_SECRET or discovery)
python scripts/sync_bosa.py --query "travaux" --limit 25 --import
```

Use `--discover` or `--force-discover` if endpoints are not yet cached. Notices are stored with `source=bosa.eprocurement` and can be filtered via the API (`?sources=BOSA`) or watchlists with `sources: ["BOSA"]`.

## API: Filter notices by source

List notices optionally filtered by source:

```powershell
# All notices (default)
curl "http://localhost:8000/api/notices"

# TED only
curl "http://localhost:8000/api/notices?sources=TED"

# BOSA only
curl "http://localhost:8000/api/notices?sources=BOSA"

# Both (comma-separated or repeated)
curl "http://localhost:8000/api/notices?sources=TED&sources=BOSA"
```

## Watchlists

Watchlists allow you to create saved searches that automatically match notices based on keywords, countries, CPV prefixes, and **data sources** (TED, BOSA, or both).

### Creating Watchlists

**Create a watchlist for TED notices only:**
```powershell
curl -X POST http://localhost:8000/api/watchlists `
  -H "Content-Type: application/json" `
  -d '{"name": "TED Solar Projects", "keywords": ["solar"], "sources": ["TED"]}'
```

**Create a watchlist for BOSA notices only:**
```powershell
curl -X POST http://localhost:8000/api/watchlists `
  -H "Content-Type: application/json" `
  -d '{"name": "BOSA Infrastructure", "keywords": ["infrastructure"], "sources": ["BOSA"]}'
```

**Create a watchlist for both sources (default):**
```powershell
curl -X POST http://localhost:8000/api/watchlists `
  -H "Content-Type: application/json" `
  -d '{"name": "All Renewable Energy", "keywords": ["renewable", "energy"], "sources": ["TED", "BOSA"]}'
```

If `sources` is omitted, it defaults to `["TED", "BOSA"]`.

### Refreshing and Viewing Matches

```powershell
# Refresh matches for a watchlist
curl -X POST http://localhost:8000/api/watchlists/{watchlist_id}/refresh

# View matches
curl http://localhost:8000/api/watchlists/{watchlist_id}/matches
```

### Backfilling Sources

If you have existing watchlists without sources set, run the seed script:

```powershell
python scripts/seed_watchlists_sources.py
```

This sets all watchlists to `["TED", "BOSA"]` by default.

### End-to-end verification (TED, BOSA, both)

After ingesting TED and BOSA notices, create three watchlists and refresh to verify matching:

```powershell
# 1) Start API
python -m uvicorn app.main:app --reload

# 2) In another terminal: ensure DB is migrated and data is present
python -m alembic upgrade head
python scripts/sync_ted.py --query "construction" --limit 25 --import
python scripts/sync_bosa.py --query "travaux" --limit 25 --import

# 3) Create watchlists: TED only, BOSA only, BOTH
curl -X POST http://localhost:8000/api/watchlists -H "Content-Type: application/json" -d "{\"name\": \"TED only\", \"keywords\": [\"construction\"], \"sources\": [\"TED\"]}"
curl -X POST http://localhost:8000/api/watchlists -H "Content-Type: application/json" -d "{\"name\": \"BOSA only\", \"keywords\": [\"travaux\"], \"sources\": [\"BOSA\"]}"
curl -X POST http://localhost:8000/api/watchlists -H "Content-Type: application/json" -d "{\"name\": \"Both sources\", \"keywords\": [\"services\"], \"sources\": [\"TED\", \"BOSA\"]}"

# 4) Refresh each watchlist (use IDs from create response)
curl -X POST http://localhost:8000/api/watchlists/{watchlist_id}/refresh

# 5) View matches
curl http://localhost:8000/api/watchlists/{watchlist_id}/matches
```

TED-only watchlists match only `ted.europa.eu` notices; BOSA-only match only `bosa.eprocurement`; "Both" matches both sources.

## BOSA e-Procurement API Configuration

The ProcureWatch API supports integration with BOSA e-Procurement APIs (Search, Location, Dossier, TUS, Config) using OAuth2 Client Credentials authentication.

### Environment Setup

1. **Configure `.env` file:**
   
   Copy `.env.example` to `.env` and fill in the required values:
   
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and set:
   - `EPROCUREMENT_ENV=INT` (or `PR` for production)
   - `EPROCUREMENT_INT_CLIENT_ID=<your_int_client_id>`
   - `EPROCUREMENT_INT_CLIENT_SECRET=<your_int_client_secret>`
   - `EPROCUREMENT_PR_CLIENT_ID=<your_pr_client_id>` (if using PR)
   - `EPROCUREMENT_PR_CLIENT_SECRET=<your_pr_client_secret>` (if using PR)
   
   **Important:** Never commit `.env` with real secrets. The `.env` file is already in `.gitignore`.

2. **Switch between INT and PR environments:**
   
   Set `EPROCUREMENT_ENV` in `.env`:
   - `EPROCUREMENT_ENV=INT` for integration environment
   - `EPROCUREMENT_ENV=PR` for production environment
   
   The system will automatically use the correct token URL, client credentials, and base URLs based on this setting.

### Discovery and Testing

1. **Discover Search API endpoints:**
   
   ```bash
   python scripts/discover_eprocurement_sea.py
   ```
   
   This script will:
   - Download the Swagger/OpenAPI specification from the Search API
   - Cache it locally in `.cache/eprocurement/sea_swagger.json`
   - List all endpoints that contain "publication", "bda", or "search" in their path/summary/operationId
   - If `EPROCUREMENT_ENDPOINT_CONFIRMED=true`, it will also test the first candidate endpoint

2. **Enable endpoint testing:**
   
   After reviewing the discovered endpoints, set in `.env`:
   ```
   EPROCUREMENT_ENDPOINT_CONFIRMED=true
   ```
   
   Then run the discovery script again to test the endpoint with a sample query.

3. **Test OAuth2 token:**
   
   ```bash
   python scripts/test_bosa_oauth.py
   ```
   
   This verifies that OAuth2 credentials are correctly configured and can obtain an access token.

### API Base URLs

The following API base URLs are configured (INT/PR):
- **Search API (Sea):** `EPROCUREMENT_INT_SEA_BASE_URL` / `EPROCUREMENT_PR_SEA_BASE_URL`
- **Location API:** `EPROCUREMENT_INT_LOC_BASE_URL` / `EPROCUREMENT_PR_LOC_BASE_URL`
- **Dossier API:** `EPROCUREMENT_INT_DOS_BASE_URL` / `EPROCUREMENT_PR_DOS_BASE_URL`
- **TUS API:** `EPROCUREMENT_INT_TUS_BASE_URL` / `EPROCUREMENT_PR_TUS_BASE_URL`
- **Config API:** `EPROCUREMENT_INT_CFG_BASE_URL` / `EPROCUREMENT_PR_CFG_BASE_URL`

Default values point to the INT environment. Override in `.env` if needed.

## Render Deployment

### Environment Variables

Set the following environment variables in Render:

- `DATABASE_URL` - Your Neon PostgreSQL connection string (must include `sslmode=require`)
- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins (e.g., `https://your-frontend.lovable.app,http://localhost:3000`)

### Build & Start Commands

- **Build Command:**
  ```bash
  pip install -r requirements.txt
  ```

- **Start Command:**
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

### Post-Deploy Script (Optional)

After deployment, run migrations:
```bash
alembic upgrade head
```

You can add this as a post-deploy script in Render or run it manually via Render's shell.

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Configuration with pydantic-settings
│   │   └── logging.py       # Logging setup
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy Base
│   │   └── session.py       # Database session management
│   └── api/
│       ├── __init__.py
│       └── routes/
│           ├── __init__.py
│           └── health.py    # Health check endpoint
├── alembic/                 # Migration scripts
├── tests/                   # Test suite
├── alembic.ini              # Alembic configuration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
└── README.md

```

## Secrets and configuration

All sensitive values (database passwords, OAuth client IDs/secrets, API keys, cookies) **must be provided via environment variables only** and **must never be committed to Git**.

- Copy `.env.example` to `.env` and fill in the placeholders:

  ```bash
  cp .env.example .env
  ```

- Required variables include (see `.env.example` for the full list):
  - `DATABASE_URL`
  - `EPROC_CLIENT_ID` / `EPROC_CLIENT_SECRET` (Belgian e-Procurement OAuth client)
  - `TED_MODE`, `TED_SEARCH_BASE_URL` (TED Search API)
  - `EMAIL_*` (SMTP or file outbox)

- The app uses `pydantic-settings` and reads from `.env` automatically via `app.core.config.Settings`.

To reduce the chance of future leaks, a simple pre-commit helper is provided:

```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/usr/bin/env bash
python scripts/pre_commit_secret_scan.py
EOF
chmod +x .git/hooks/pre-commit
```

This will block commits that contain obvious secrets such as `client_secret` or inline Bearer tokens.


## API Endpoints

### GET /
Returns application name and status.

**Response:**
```json
{
  "name": "procurewatch-api",
  "status": "running"
}
```

### GET /health
Health check endpoint with database connectivity check.

**Success Response (200):**
```json
{
  "status": "ok",
  "db": "ok"
}
```

**Degraded Response (503):**
```json
{
  "detail": {
    "status": "degraded",
    "db": "error"
  }
}
```

## License

Proprietary - ProcureWatch
