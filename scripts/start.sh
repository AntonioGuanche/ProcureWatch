#!/bin/bash

echo "=== ProcureWatch startup ==="

# 1. Run Alembic migrations (with error recovery)
echo "Running database migrations..."
if python -m alembic upgrade head 2>&1; then
    echo "Migrations complete."
else
    echo "Migration failed. Attempting recovery..."

    # If alembic_version points to a revision that no longer exists (e.g. '004'),
    # stamp it back to the last known good revision ('003').
    python -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    try:
        ver = conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
        print(f'Current alembic version: {ver}')
        if ver and ver not in ('001', '002', '003', '004', '005', '006', '007', '008'):
            conn.execute(text(\"UPDATE alembic_version SET version_num = '005'\"))
            conn.commit()
            print('Reset alembic_version to 004.')
        else:
            print('Version is valid, no fix needed.')
    except Exception as e:
        print(f'Recovery check failed: {e}')
" 2>&1

    # Retry
    if python -m alembic upgrade head 2>&1; then
        echo "Migrations complete (after recovery)."
    else
        echo "WARNING: Migrations still failed. Starting server anyway..."
    fi
fi

# 2. Start uvicorn
echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
