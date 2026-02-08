#!/bin/bash
set -e

echo "=== ProcureWatch startup ==="

# 1. Run Alembic migrations (idempotent)
echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations complete."

# 2. Start uvicorn
echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
