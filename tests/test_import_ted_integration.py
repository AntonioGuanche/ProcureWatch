"""Integration test: run migrations, import TED file, verify Notice rows exist."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup (with retry for Windows file locks)
    import time
    for _ in range(3):
        try:
            if db_path.exists():
                db_path.unlink()
            break
        except PermissionError:
            time.sleep(0.1)


def test_import_ted_integration_with_migrations(temp_db):
    """Integration test: migrations + import + verify Notice rows."""
    db_url = f"sqlite:///{temp_db.as_posix()}"
    
    # 1) Run migrations
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": db_url},
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Migrations failed: {result.stderr}"
    
    # 2) Create a minimal TED raw JSON file
    ted_data = {
        "metadata": {"term": "test", "page": 1, "pageSize": 1},
        "json": {
            "notices": [
                {
                    "publication-number": "TED-INTEGRATION-001",
                    "notice-title": {"eng": "Integration Test Notice", "fra": "Avis de test d'intégration"},
                    "buyer-country": "BE",
                    "main-classification-proc": "45000000",
                    "publication-date": "2026-02-10",
                },
            ],
            "totalCount": 1,
        },
    }
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(ted_data, f, indent=2)
        ted_file = Path(f.name)
    
    try:
        # 3) Run import
        result = subprocess.run(
            [sys.executable, "-m", "ingest.import_ted", str(ted_file), "--db-url", db_url],
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        
        # 4) Verify Notice row exists
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.notice import Notice
        
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        try:
            notice = db.query(Notice).filter(
                Notice.source == "TED_EU",
                Notice.source_id == "TED-INTEGRATION-001",
            ).first()
            assert notice is not None
            assert notice.title == "Integration Test Notice"
            # country is derived from NUTS codes in ProcurementNotice
            assert notice.cpv_main_code == "45000000"
        finally:
            db.close()
    finally:
        if ted_file.exists():
            ted_file.unlink()
