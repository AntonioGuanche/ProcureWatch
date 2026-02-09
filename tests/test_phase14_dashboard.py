"""Phase 14: Dashboard KPI endpoint tests."""
import os
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Fresh app with test DB populated with sample notices."""
    db_path = tmp_path / "test_dashboard.db"
    db_url = f"sqlite:///{db_path}"
    with patch.dict(os.environ, {"DATABASE_URL": db_url, "ADMIN_API_KEY": ""}):
        from importlib import reload
        import app.core.config as cfg; reload(cfg)
        import app.core.auth as auth; reload(auth)
        import app.core.security as sec; reload(sec)
        import app.db.session as sess; reload(sess)
        import app.api.routes.dashboard as dash; reload(dash)
        import app.api.routes.admin as adm; reload(adm)
        import app.api.routes.notices as not_; reload(not_)
        import app.api.routes.filters as fil; reload(fil)
        import app.api.routes.auth as au; reload(au)
        try:
            import app.api.routes.watchlists_mvp as wl; reload(wl)
        except Exception:
            pass
        import app.main as main; reload(main)

        from app.db.session import engine
        from app.models.notice import Base
        Base.metadata.create_all(bind=engine)

        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            conn.execute(sql_text("""
                CREATE TABLE IF NOT EXISTS import_runs (
                    id TEXT PRIMARY KEY, source TEXT,
                    started_at TIMESTAMP, completed_at TIMESTAMP,
                    created_count INTEGER DEFAULT 0, updated_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0, errors_json TEXT, search_criteria_json TEXT
                )
            """))
            conn.commit()

        # Insert sample notices
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            from uuid import uuid4
            for i in range(5):
                db.execute(sql_text("""
                    INSERT INTO notices (id, source_id, source, publication_workspace_id,
                        title, cpv_main_code, publication_date, deadline,
                        notice_type, created_at, updated_at, migrated)
                    VALUES (:id, :sid, :src, :pwid,
                        :title, :cpv, :pub_date, :deadline,
                        :ntype, :created, :updated, 0)
                """), {
                    "id": str(uuid4()),
                    "sid": f"TEST-{i}",
                    "src": "BOSA_EPROC" if i < 3 else "TED_EU",
                    "pwid": f"PW-{i}",
                    "title": f"Test notice {i}",
                    "cpv": f"4500000{i}-7",
                    "pub_date": (date.today() - timedelta(days=i)).isoformat(),
                    "deadline": (now + timedelta(days=10-i)).isoformat() if i < 4 else None,
                    "ntype": "ACTIVE" if i < 4 else "CLOSED",
                    "created": now.isoformat(),
                    "updated": now.isoformat(),
                })
            db.commit()
        finally:
            db.close()

        yield TestClient(main.app)


class TestDashboardOverview:

    def test_overview_returns_200(self, client):
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code == 200

    def test_overview_structure(self, client):
        data = client.get("/api/dashboard/overview").json()
        assert data["total_notices"] == 5
        assert data["active_notices"] >= 1
        assert "by_source" in data
        assert "BOSA_EPROC" in data["by_source"]
        assert "value_stats" in data
        assert "added_24h" in data
        assert "expiring_7d" in data

    def test_overview_source_counts(self, client):
        data = client.get("/api/dashboard/overview").json()
        assert data["by_source"]["BOSA_EPROC"] == 3
        assert data["by_source"]["TED_EU"] == 2


class TestDashboardTrends:

    def test_trends_default(self, client):
        resp = client.get("/api/dashboard/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30
        assert data["group_by"] == "day"
        assert isinstance(data["data"], list)

    def test_trends_custom_days(self, client):
        data = client.get("/api/dashboard/trends?days=7").json()
        assert data["period_days"] == 7

    def test_trends_has_data(self, client):
        data = client.get("/api/dashboard/trends?days=7").json()
        assert len(data["data"]) > 0
        assert "totals_by_source" in data


class TestDashboardTopCPV:

    def test_top_cpv_returns_data(self, client):
        resp = client.get("/api/dashboard/top-cpv")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) > 0
        entry = data["data"][0]
        assert "code" in entry
        assert "label" in entry
        assert "count" in entry

    def test_top_cpv_active_only(self, client):
        data = client.get("/api/dashboard/top-cpv?active_only=true").json()
        assert data["active_only"] is True


class TestDashboardTopAuthorities:

    def test_top_authorities_returns_200(self, client):
        """Should return 200 even with no organisation_names populated."""
        resp = client.get("/api/dashboard/top-authorities")
        assert resp.status_code == 200


class TestDashboardHealth:

    def test_health_returns_200(self, client):
        resp = client.get("/api/dashboard/health")
        assert resp.status_code == 200

    def test_health_structure(self, client):
        data = client.get("/api/dashboard/health").json()
        assert "imports" in data
        assert "freshness" in data
        assert "field_fill_rates_pct" in data
        assert "title" in data["field_fill_rates_pct"]

    def test_health_fill_rates(self, client):
        data = client.get("/api/dashboard/health").json()
        # Title is populated for all 5 notices
        assert data["field_fill_rates_pct"]["title"] == 100.0
        # CPV is populated for all 5
        assert data["field_fill_rates_pct"]["cpv_main_code"] == 100.0
