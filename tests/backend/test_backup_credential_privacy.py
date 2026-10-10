import secrets
import pytest
from sqlalchemy.engine import URL, make_url

from backend.app.services.backup_service import BackupError, _postgres_subprocess_connection


def test_backup_connection_preserves_parameters_without_password_arguments(monkeypatch):
    password = secrets.token_urlsafe(32) + "@:/%"
    original = URL.create("postgresql+psycopg2", username="test-reader", password=password,
                          host="localhost", port=5432, database="rotation_test_backup",
                          query={"sslmode": "require"}).render_as_string(hide_password=False)
    monkeypatch.setenv("PGPASSWORD", "test-only-password")
    connection, child_env = _postgres_subprocess_connection(original)
    parsed = make_url(connection)
    assert parsed.password is None
    assert password not in connection
    assert child_env["PGPASSWORD"] == password
    assert parsed.drivername == "postgresql"
    assert (parsed.host, parsed.port, parsed.database, parsed.query["sslmode"]) == (
        "localhost", 5432, "rotation_test_backup", "require")
    import os
    assert os.environ["PGPASSWORD"] == "test-only-password"


def test_password_query_or_invalid_url_never_echoes_input():
    value = secrets.token_urlsafe(32)
    for original in (value, URL.create("postgresql", host="localhost",
                                      query={"password": value}).render_as_string(hide_password=False)):
        with pytest.raises(BackupError) as caught:
            _postgres_subprocess_connection(original)
        assert value not in str(caught.value)


def test_dump_and_restore_both_use_password_free_process_arguments(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from subprocess import CompletedProcess
    from backend.app.services.backup_service import BackupService

    password = secrets.token_urlsafe(32)
    database_url = URL.create("postgresql", username="test-reader", password=password,
                              host="localhost", database="rotation_test_backup").render_as_string(hide_password=False)
    settings = SimpleNamespace(database_url=database_url, environment="test", app_version="test",
                               backup_root=str(tmp_path / "backups"), backup_s3_enabled=False,
                               backup_retention_days=30, artifact_root=str(tmp_path / "absent"))
    invoked = []

    def execute(command, **kwargs):
        if command[0] in {"pg_dump", "psql"}:
            assert all(password not in arg for arg in command)
            assert kwargs["env"]["PGPASSWORD"] == password
            invoked.append(command[0])
            if command[0] == "pg_dump":
                Path(command[command.index("--file") + 1]).write_text("-- isolated test dump\n")
        return CompletedProcess(command, 0, stdout="test-revision", stderr="")

    monkeypatch.setattr("backend.app.services.backup_service.subprocess.run", execute)
    service = BackupService(settings)
    backup = service.create_backup()
    service.restore_backup(backup.backup_id, database_url)
    assert invoked == ["pg_dump", "psql"]
