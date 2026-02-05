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
   ```bash
   cp .env.example .env
   ```
   
   The `.env` file is required for local development. Edit `.env` and set your `DATABASE_URL`:
   
   **For local development (recommended):**
   ```
   DATABASE_URL=sqlite+pysqlite:///./dev.db
   ```
   This creates a persistent `dev.db` file in the project root. Your data will persist between server restarts.
   
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
   ```bash
   python -m alembic upgrade head
   ```

5. **Run database migrations:**
   ```bash
   python -m alembic upgrade head
   ```
   
   **Note:** Run migrations after:
   - First-time setup
   - Switching database URLs
   - Pulling new migrations from the repository

6. **Start the development server:**
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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

```bash
pytest
```

## Database Migrations

### Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

### Apply migrations:
```bash
alembic upgrade head
```

### Rollback last migration:
```bash
alembic downgrade -1
```

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
