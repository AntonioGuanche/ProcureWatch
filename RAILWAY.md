# Railway Deployment Guide

## Architecture

```
Railway Project
├── web service     → Procfile: bash scripts/start.sh
│                     (API + auto migrations on deploy)
├── cron service    → python scripts/cron_import.py
│                     (daily import, schedule: 0 6 * * *)
└── PostgreSQL      → shared database
```

## 1. Web Service (already deployed)

The `Procfile` runs `scripts/start.sh` which:
1. Runs `alembic upgrade head` (idempotent, safe on every deploy)
2. Starts `uvicorn app.main:app`

## 2. Cron Service Setup

### Option A: Railway Cron Service (recommended)

1. In your Railway project, click **+ New** → **Service**
2. Connect the **same GitHub repo**
3. Settings:
   - **Start command**: `python scripts/cron_import.py`
   - **Schedule**: `0 6 * * *` (daily at 06:00 UTC = 07:00 CET)
   - **Region**: Same as web service
4. **Variables** tab → **Reference** the same database:
   - `DATABASE_URL` → reference from Postgres service
   - Copy all `EPROCUREMENT_*` and `TED_*` vars from web service
5. Optional env vars:
   - `IMPORT_SOURCES=BOSA,TED`
   - `IMPORT_TERM=*`
   - `IMPORT_DAYS_BACK=3`
   - `IMPORT_PAGE_SIZE=100`
   - `IMPORT_MAX_PAGES=10`
   - `IMPORT_ALERT_EMAIL=you@example.com`

### Option B: Manual trigger via API

No cron needed — use the admin endpoint:

```bash
curl -X POST "https://your-app.railway.app/api/admin/import?sources=BOSA,TED&term=*&page_size=25&max_pages=1"
```

## 3. Monitoring

### Health check
```
GET /health
```
Returns: `{ status, db, notices, last_import: { source, at, created, updated, errors } }`

### Import runs
```
GET /api/admin/import-runs           # Last 20 runs
GET /api/admin/import-runs?source=BOSA&limit=5
GET /api/admin/import-runs/summary   # Aggregated stats per source
```

## 4. Environment Variables

### Required (web + cron)
| Variable | Example |
|---|---|
| `DATABASE_URL` | `postgresql://...` (from Railway Postgres) |
| `EPROCUREMENT_INT_CLIENT_ID` | Your BOSA OAuth2 client ID |
| `EPROCUREMENT_INT_CLIENT_SECRET` | Your BOSA OAuth2 client secret |

### Optional
| Variable | Default | Description |
|---|---|---|
| `TED_MODE` | `official` | `official` or `off` |
| `EPROC_MODE` | `auto` | `official`, `playwright`, or `auto` |
| `EMAIL_MODE` | `file` | `file` or `smtp` |
| `JWT_SECRET_KEY` | `change-me-in-production` | **Change this!** |
| `ALLOWED_ORIGINS` | `*` | CORS origins |
| `IMPORT_ALERT_EMAIL` | (none) | Alert on high error rate |

## 5. Troubleshooting

### Check database state
```
GET /health                          → notice count + last import
GET /api/admin/import-runs/summary   → totals per source
```

### Manual import test
```bash
# Small test: 1 page of 5 results from BOSA only
curl -X POST "https://your-app.railway.app/api/admin/import?sources=BOSA&term=travaux&page_size=5&max_pages=1"
```

### View logs
Railway dashboard → Service → Logs tab
