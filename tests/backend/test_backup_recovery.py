"""Production backup recovery contracts; only synthetic data and mocked S3."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import sqlite3

import boto3
import pytest
from moto import mock_aws
from botocore.response import StreamingBody

from backend.app.services.backup_service import BackupError, BackupService, CorruptBackupError, S3BackupStorage
from scripts.backup_db import _load_backup_settings


def settings(tmp_path, **overrides):
    values = dict(database_url=f"sqlite:///{tmp_path / 'source.db'}", environment="production",
        app_version="fixture", backup_root=str(tmp_path / 'staging'), backup_retention_days=1,
        backup_retention_enabled=False, backup_s3_enabled=True, backup_s3_endpoint_url=None,
        backup_s3_bucket="backup-fixture", backup_s3_access_key="testing", backup_s3_secret_key="testing",
        backup_s3_region="us-east-1", artifact_root=str(tmp_path / 'absent-artifacts'))
    return SimpleNamespace(**(values | overrides))


def seed_database(config):
    with sqlite3.connect(config.database_url.split("///", 1)[1]) as db:
        db.execute("CREATE TABLE fixture (value TEXT)")
        db.execute("INSERT INTO fixture VALUES ('isolated recovery')")


def test_railway_physical_region_rejected_before_any_request(tmp_path, monkeypatch):
    client = Mock()
    monkeypatch.setattr(boto3, "client", client)
    with pytest.raises(BackupError, match="S3_SIGNING_REGION"):
        S3BackupStorage(settings(tmp_path, backup_s3_endpoint_url="https://t3.storageapi.dev",
                                 backup_s3_region="iad"), tmp_path / 'staging')
    client.assert_not_called()


def test_railway_client_explicit_sigv4_auto_virtual_host(tmp_path, monkeypatch):
    client = Mock()
    monkeypatch.setattr(boto3, "client", client)
    S3BackupStorage(settings(tmp_path, backup_s3_endpoint_url="https://t3.storageapi.dev",
                             backup_s3_region="auto"), tmp_path / 'staging')
    options = client.call_args.kwargs
    assert options["region_name"] == "auto"
    assert options["config"].signature_version == "s3v4"
    assert options["config"].s3["addressing_style"] == "virtual"
    assert options["config"].retries["total_max_attempts"] == 3


@mock_aws
def test_verified_s3_backup_restore_preserves_old_objects_and_cleans_staging(tmp_path, monkeypatch):
    config = settings(tmp_path)
    seed_database(config)
    service = BackupService(config)
    client = service._s3._client
    client.create_bucket(Bucket=config.backup_s3_bucket)
    client.put_object(Bucket=config.backup_s3_bucket, Key="old-backup.sql", Body=b"historical archive")
    retention = Mock(side_effect=AssertionError("Retention is forbidden in recovery"))
    monkeypatch.setattr(service, "_apply_retention", retention)
    metadata = service.create_backup()
    assert metadata.size_bytes > 0
    payload = client.get_object(Bucket=config.backup_s3_bucket, Key=metadata.backup_id + ".db")["Body"].read()
    assert hashlib.sha256(payload).hexdigest() == metadata.checksum_sha256
    assert client.get_object(Bucket=config.backup_s3_bucket, Key="old-backup.sql")["Body"].read() == b"historical archive"
    assert not list(service.root.iterdir())
    retention.assert_not_called()
    target = tmp_path / "restored.db"
    service.restore_backup(metadata.backup_id, f"sqlite:///{target}")
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT value FROM fixture").fetchone() == ("isolated recovery",)


@mock_aws
@pytest.mark.parametrize("failure", ["size", "sha256"])
def test_remote_corruption_never_publishes_manifest_or_runs_retention(tmp_path, monkeypatch, failure):
    config = settings(tmp_path)
    seed_database(config)
    service = BackupService(config)
    client = service._s3._client
    client.create_bucket(Bucket=config.backup_s3_bucket)
    client.put_object(Bucket=config.backup_s3_bucket, Key="old-backup.sql", Body=b"keep")
    retention = Mock()
    monkeypatch.setattr(service, "_apply_retention", retention)
    if failure == "size":
        monkeypatch.setattr(client, "head_object", lambda **kwargs: {"ContentLength": 0})
    else:
        monkeypatch.setattr(client, "get_object", lambda **kwargs: {"Body": StreamingBody(BytesIO(b"corrupt"), 7)})
    with pytest.raises(CorruptBackupError, match="S3_VERIFY"):
        service.create_backup()
    names = service._s3.list_names()
    assert "old-backup.sql" in names
    assert not any(name.endswith(".json") for name in names)
    assert not list(service.root.iterdir())
    retention.assert_not_called()


def test_s3_error_does_not_echo_provider_exception(tmp_path, monkeypatch):
    client = Mock()
    client.upload_file.side_effect = RuntimeError("SignatureDoesNotMatch fixture-sensitive-echo")
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    store = S3BackupStorage(settings(tmp_path), tmp_path / 'staging')
    path = store.root / "fixture.sql"
    path.write_bytes(b"synthetic SQL")
    with pytest.raises(BackupError, match="SignatureDoesNotMatch") as exc:
        store.upload(path)
    assert "fixture-sensitive-echo" not in str(exc.value)


def test_cli_retention_is_off_and_incomplete_references_fail_closed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///fixture.db")
    for name in ("BACKUP_S3_ACCESS_KEY", "BACKUP_S3_SECRET_KEY", "BACKUP_S3_BUCKET", "BACKUP_RETENTION_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    assert _load_backup_settings().backup_retention_enabled is False
    monkeypatch.setenv("BACKUP_S3_BUCKET", "backup-fixture")
    with pytest.raises(RuntimeError, match="S3_CONFIG_INCOMPLETE"):
        _load_backup_settings()
    monkeypatch.setenv("BACKUP_S3_ACCESS_KEY", "${{bucket.ACCESS_KEY_ID}}")
    monkeypatch.setenv("BACKUP_S3_SECRET_KEY", "${{bucket.SECRET_ACCESS_KEY}}")
    with pytest.raises(RuntimeError, match="S3_REFERENCE_UNRESOLVED"):
        _load_backup_settings()


def test_postgres_password_not_in_process_arguments(tmp_path, monkeypatch):
    from backend.app.services import backup_service
    captured = {}
    def run(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(backup_service.subprocess, "run", run)
    fixture_password = "non-sensitive" + "-fixture-value"
    backup_service._postgres_run(f"postgresql://fixture:{fixture_password}@localhost/fixture?sslmode=require",
                                ["pg_dump"], timeout=1)
    assert fixture_password not in str(captured["argv"])
    assert captured["env"]["PGPASSWORD"] == fixture_password
    assert captured["argv"][-1].endswith("/fixture?sslmode=require")


@mock_aws
def test_postgres18_dump_s3_restore_in_isolated_ci_database(tmp_path):
    import os
    import subprocess
    from urllib.parse import urlsplit
    from uuid import uuid4
    import psycopg2
    from psycopg2 import sql
    source = os.getenv("BACKUP_TEST_POSTGRES_URL")
    if not source:
        pytest.skip("Requires isolated CI PostgreSQL 18; never uses DATABASE_URL")
    parsed = urlsplit(source)
    assert os.getenv("BACKUP_TEST_ISOLATED") == "true"
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path == "/backup_fixture"
    assert "18." in subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True).stdout
    target_db = "backup_restore_" + uuid4().hex[:12]
    with psycopg2.connect(source) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE recovery_fixture (tenant text, value integer)")
            cur.execute("INSERT INTO recovery_fixture VALUES ('tenant-a', 17), ('tenant-b', 29)")
    admin = psycopg2.connect(source)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
    admin.close()
    config = settings(tmp_path, database_url=source)
    service = BackupService(config)
    service._s3._client.create_bucket(Bucket=config.backup_s3_bucket)
    metadata = service.create_backup()
    assert metadata.database_type == "postgresql"
    assert metadata.size_bytes > 0
    target = parsed._replace(path="/" + target_db).geturl()
    service.restore_backup(metadata.backup_id, target)
    with psycopg2.connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant, value FROM recovery_fixture ORDER BY tenant")
            assert cur.fetchall() == [("tenant-a", 17), ("tenant-b", 29)]
    # Empty destination only: SQL errors must fail, never produce false success.
    broken = tmp_path / "invalid.sql"
    broken.write_text("THIS IS NOT VALID SQL;", encoding="utf-8")
    from backend.app.services.backup_service import _postgres_run
    result = _postgres_run(target, ["psql", "--set=ON_ERROR_STOP=1", "-f", str(broken)], timeout=30)
    assert result.returncode != 0
