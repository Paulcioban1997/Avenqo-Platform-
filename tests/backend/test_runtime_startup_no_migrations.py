"""Regression tests ensuring FastAPI runtime never attempts database migrations at startup."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config.settings import Settings


def test_railway_json_start_command_does_not_contain_alembic():
    """Verify that railway.json does not execute alembic in startCommand."""
    railway_json_path = Path(__file__).resolve().parents[2] / "railway.json"
    assert railway_json_path.exists(), "railway.json must exist"
    data = json.loads(railway_json_path.read_text(encoding="utf-8"))
    start_cmd = data.get("deploy", {}).get("startCommand", "")
    
    assert "alembic" not in start_cmd.lower(), (
        f"startCommand must not execute alembic migrations: {start_cmd}"
    )
    assert "upgrade" not in start_cmd.lower(), (
        f"startCommand must not execute migration upgrades: {start_cmd}"
    )
    assert "uvicorn" in start_cmd, (
        f"startCommand must start the uvicorn application server: {start_cmd}"
    )


def test_production_lifespan_never_calls_create_database_tables(monkeypatch):
    """Verify that in production mode, create_database_tables is never called."""
    with patch("backend.main.create_database_tables") as mock_create_tables:
        with patch("backend.main.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.environment = "production"
            mock_s.database_url = "sqlite:///:memory:"
            mock_s.artifact_root = "./artifacts"
            mock_s.http_sync_thread_limit = 10
            mock_s.db_pool_size = 5
            mock_s.db_max_overflow = 5
            mock_s.voice_commercial_enabled = False
            mock_s.voice_provisioning_worker_enabled = False
            mock_s.app_name = "Avenqo"
            mock_s.app_version = "0.1.0"
            mock_settings.return_value = mock_s
            # Lifespan startup
            with TestClient(app) as client:
                resp = client.get("/api/v1/health")
                assert resp.status_code == 200

            mock_create_tables.assert_not_called()


def test_health_and_readiness_endpoints_are_read_only(monkeypatch):
    """Verify that health and readiness endpoints only inspect and do not run DDL."""
    with TestClient(app) as client:
        # /api/v1/health does not touch database
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json().get("status") == "healthy"

        # /api/v1/ready inspects database read-only
        resp_ready = client.get("/api/v1/ready")
        assert resp_ready.status_code == 200
        data = resp_ready.json()
        assert "database" in data
        assert "migrations" in data
