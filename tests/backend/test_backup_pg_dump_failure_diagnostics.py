"""Backup failures must be actionable without leaking database credentials."""

from subprocess import CompletedProcess, TimeoutExpired
from types import SimpleNamespace
import secrets

import pytest
from sqlalchemy.engine import URL

from backend.app.services.backup_service import BackupError, BackupService
from scripts.backup_db import _load_backup_settings


@pytest.fixture
def backup_service(tmp_path):
    password = secrets.token_urlsafe(24)
    database_url = URL.create(
        "postgresql", username="app", password=password, host="localhost", port=5432,
        database="avenqo"
    ).render_as_string(hide_password=False)
    settings = SimpleNamespace(
        database_url=database_url,
        environment="test",
        app_version="test",
        backup_root=str(tmp_path / "backups"),
        backup_s3_enabled=False,
        backup_retention_days=30,
        artifact_root=str(tmp_path / "artifacts"),
    )
    return BackupService(settings)


@pytest.mark.parametrize(
    ("stderr", "category"),
    [
        ("query failed: ERROR: query would be affected by row-level security policy for table accounting_invoices", "row_level_security"),
        ("permission denied for table accounting_invoices", "insufficient_privileges"),
        ("server version mismatch", "client_server_version_mismatch"),
        ("password authentication failed", "authentication_failed"),
        ("could not translate host name", "dns_resolution_failed"),
    ],
)
def test_pg_dump_error_is_categorized_without_stderr_or_partial_file(
    backup_service, monkeypatch, stderr, category
):
    password = secrets.token_urlsafe(24)

    def failing_dump(command, **_kwargs):
        from pathlib import Path

        Path(command[command.index("--file") + 1]).write_text("partial")
        return CompletedProcess(command, 1, stderr=stderr + " " + password)

    monkeypatch.setattr("backend.app.services.backup_service.subprocess.run", failing_dump)
    with pytest.raises(BackupError, match=f"catégorie : {category}") as caught:
        backup_service.create_backup()
    assert password not in str(caught.value)
    assert not list(backup_service.root.glob("*.sql"))


def test_pg_dump_timeout_discards_partial_file(backup_service, monkeypatch):
    def hanging_dump(command, **_kwargs):
        from pathlib import Path

        Path(command[command.index("--file") + 1]).write_text("partial")
        raise TimeoutExpired(command, 600)

    monkeypatch.setattr("backend.app.services.backup_service.subprocess.run", hanging_dump)
    with pytest.raises(BackupError, match="catégorie : timeout"):
        backup_service.create_backup()
    assert not list(backup_service.root.glob("*.sql"))


def test_dedicated_backup_login_must_target_same_database(monkeypatch):
    app_password = secrets.token_urlsafe(24)
    backup_password = secrets.token_urlsafe(24)
    def db_url(user, password, host):
        return URL.create(
            "postgresql", username=user, password=password, host=host,
            port=5432, database="avenqo"
        ).render_as_string(hide_password=False)

    monkeypatch.setenv("DATABASE_URL", db_url("app", app_password, "db"))
    monkeypatch.setenv("BACKUP_DATABASE_URL", db_url("backup", backup_password, "db"))
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    settings = _load_backup_settings()
    assert settings.database_url.startswith("postgresql://backup:")

    monkeypatch.setenv("BACKUP_DATABASE_URL", db_url("backup", backup_password, "other"))
    with pytest.raises(RuntimeError, match="même serveur") as caught:
        _load_backup_settings()
    assert backup_password not in str(caught.value)
