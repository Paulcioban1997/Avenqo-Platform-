from types import SimpleNamespace
import sqlite3
import pytest
from moto import mock_aws

from backend.app.services.backup_service import BackupService, S3BackupStorage
from scripts.validate_backup67_sandbox import PrefixClient, inventory, run, SANDBOX
from scripts.validate_backup67_sandbox import fixture_dsn, pg, sql
from backend.app.services.backup_service import _postgres_run
from urllib.parse import parse_qs, urlsplit
import subprocess


@pytest.mark.parametrize("environment,bucket", [("production", "forbidden"), (SANDBOX, "production-bucket")])
def test_guard_rejects_non_sandbox_and_wrong_bucket_before_any_database(monkeypatch, environment, bucket):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", environment)
    monkeypatch.setenv("BACKUP_S3_BUCKET", bucket)
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", "https://t3.storageapi.dev")
    with pytest.raises(RuntimeError):
        run()


@mock_aws
def test_namespace_exercises_unchanged_backup_code_without_touching_old_archives(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE synthetic (value integer)")
        db.execute("INSERT INTO synthetic VALUES (17)")
    config = SimpleNamespace(database_url=f"sqlite:///{source}", environment="sandbox",
        app_version="fixture", backup_s3_endpoint_url=None, backup_s3_bucket="backup-fixture",
        backup_s3_access_key="testing", backup_s3_secret_key="testing", backup_s3_region="us-east-1",
        backup_root=str(tmp_path / "staging"), backup_retention_days=1, backup_retention_enabled=False,
        artifact_root=str(tmp_path / "absent"))
    store = S3BackupStorage(config, tmp_path / "staging")
    raw = store._client
    raw.create_bucket(Bucket="backup-fixture")
    raw.put_object(Bucket="backup-fixture", Key="sandbox/old.sql", Body=b"keep")
    before = inventory(raw, "backup-fixture")
    prefix = "qa/pr67/fixture/"
    store._client = PrefixClient(raw, "backup-fixture", prefix)
    service = BackupService(config, storage=store)
    meta = service.create_backup()
    assert meta.backup_id + ".json" in store.list_names()
    service.restore_backup(meta.backup_id, f"sqlite:///{tmp_path / 'restored.db'}")
    with sqlite3.connect(tmp_path / "restored.db") as db:
        assert db.execute("SELECT value FROM synthetic").fetchone() == (17,)
    after = inventory(raw, "backup-fixture")
    assert all(after[k] == v for k, v in before.items())
    assert all(k.startswith(prefix) for k in after.keys() - before.keys())
    with pytest.raises(AssertionError, match="deletion forbidden"):
        store.delete(meta.backup_id + ".sql")


@pytest.mark.parametrize("database", ["postgres", "backup_fixture", "restore_fixture"])
def test_fixture_uri_survives_actual_backup_normalization(monkeypatch, tmp_path, database):
    captured = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kwargs:
        captured.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    socket = tmp_path / "private socket"
    _postgres_run(fixture_dsn(database, socket), ["psql"], timeout=1)
    actual = captured[0][-1]
    assert actual.startswith("postgresql://")
    parts = urlsplit(actual)
    assert parts.path == "/" + database
    assert parts.username == "qa_runtime"
    assert parse_qs(parts.query)["host"] == [str(socket)]
    with pytest.raises(ValueError, match="fixture_database_required"):
        fixture_dsn("real_client_database", socket)


@pytest.mark.parametrize("runner", [lambda: pg(["initdb"]), lambda: sql("unused", "unused")])
def test_command_diagnostics_do_not_disclose_output_or_environment(monkeypatch, capsys, runner):
    private = "fixture-sensitive-output-do-not-log"
    monkeypatch.setenv("DATABASE_URL", private)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(returncode=7, stdout=private, stderr="Permission denied " + private))
    with pytest.raises(RuntimeError):
        runner()
    output = capsys.readouterr().out
    assert private not in output
    assert '"returncode": 7' in output
    assert '"reason": "permission_denied"' in output
