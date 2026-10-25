"""Séparation Production/Sandbox des sauvegardes et restauration isolée."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from moto import mock_aws

from backend.app.services.backup_service import (
    BackupEnvironmentError,
    BackupService,
    resolve_backup_environment,
)


def _sqlite_url(db_path: Path) -> str:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _sqlite_file(url: str) -> Path:
    if "sqlite:///" not in url:
        raise ValueError("URL SQLite attendue")
    return Path(url.split("sqlite:///", 1)[1])


def _settings(tmp_path: Path, environment: str, monkeypatch):
    from types import SimpleNamespace

    db_path = tmp_path / f"{environment}.db"
    backup_root = tmp_path / "staging" / environment
    artifact_root = tmp_path / "artifacts" / environment
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    database_url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))
    monkeypatch.delenv("BACKUP_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "avenqo-backups")
    monkeypatch.setenv("BACKUP_S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("BACKUP_S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("BACKUP_S3_REGION", "us-east-1")
    return SimpleNamespace(
        database_url=database_url,
        environment=environment,
        app_version="0.1.0",
        backup_root=str(backup_root),
        backup_retention_days=30,
        backup_s3_enabled=True,
        backup_s3_endpoint_url=None,
        backup_s3_bucket="avenqo-backups",
        backup_s3_access_key="test-access",
        backup_s3_secret_key="test-secret",
        backup_s3_region="us-east-1",
        artifact_root=str(artifact_root),
    )


def _seed_sqlite(url: str, value: str) -> None:
    import sqlite3

    src = _sqlite_file(url)
    src.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _make_bucket():
    import boto3

    client = boto3.client(
        "s3",
        aws_access_key_id="test-access",
        aws_secret_access_key="test-secret",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket="avenqo-backups")
    return client


def test_resolve_backup_environment_uses_railway_when_explicit_missing() -> None:
    assert resolve_backup_environment(None, "sandbox") == "sandbox"


def test_resolve_backup_environment_rejects_contradiction() -> None:
    with pytest.raises(BackupEnvironmentError, match="contredit"):
        resolve_backup_environment("production", "sandbox")


def test_resolve_backup_environment_requires_a_value() -> None:
    with pytest.raises(BackupEnvironmentError, match="requis"):
        resolve_backup_environment("", "")


@mock_aws
def test_prefixed_backups_stay_isolated_between_production_and_sandbox(
    tmp_path, monkeypatch
) -> None:
    _make_bucket()
    prod_settings = _settings(tmp_path / "prod", "production", monkeypatch)
    _seed_sqlite(prod_settings.database_url, "prod-row")
    prod = BackupService(prod_settings)
    prod_meta = prod.create_backup()

    sandbox_settings = _settings(tmp_path / "sandbox", "sandbox", monkeypatch)
    _seed_sqlite(sandbox_settings.database_url, "sandbox-row")
    sandbox = BackupService(sandbox_settings)
    sandbox_meta = sandbox.create_backup()

    names = set(prod._s3.list_names())
    assert f"production/{prod_meta.backup_id}.json" in names
    assert f"sandbox/{sandbox_meta.backup_id}.json" in names
    assert f"{prod_meta.backup_id}.json" not in names
    assert prod_meta.environment == "production"
    assert sandbox_meta.environment == "sandbox"


@mock_aws
def test_restore_reads_legacy_flat_keys_and_new_prefixed_keys(tmp_path, monkeypatch) -> None:
    client = _make_bucket()
    settings = _settings(tmp_path, "production", monkeypatch)
    _seed_sqlite(settings.database_url, "legacy-row")
    service = BackupService(settings)
    metadata = service.create_backup()

    # Copie une sauvegarde préfixée vers l'ancien format plat pour prouver la lecture.
    prefixed_sql = f"production/{metadata.backup_id}.db"
    prefixed_json = f"production/{metadata.backup_id}.json"
    client.copy_object(
        Bucket="avenqo-backups",
        CopySource={"Bucket": "avenqo-backups", "Key": prefixed_json},
        Key=f"{metadata.backup_id}.json",
    )
    client.copy_object(
        Bucket="avenqo-backups",
        CopySource={"Bucket": "avenqo-backups", "Key": prefixed_sql},
        Key=f"{metadata.backup_id}.db",
    )
    client.delete_object(Bucket="avenqo-backups", Key=prefixed_sql)
    client.delete_object(Bucket="avenqo-backups", Key=prefixed_json)
    for suffix in (".db", ".json"):
        (service.root / f"{metadata.backup_id}{suffix}").unlink(missing_ok=True)

    target = tmp_path / "restored-legacy.db"
    service.restore_backup(metadata.backup_id, _sqlite_url(target))
    import sqlite3

    conn = sqlite3.connect(str(target))
    assert conn.execute("SELECT v FROM t").fetchone() == ("legacy-row",)
    conn.close()


@mock_aws
def test_retention_uses_created_at_and_never_deletes_legacy_objects(
    tmp_path, monkeypatch
) -> None:
    client = _make_bucket()
    settings = _settings(tmp_path, "production", monkeypatch)
    settings.backup_retention_days = 30
    _seed_sqlite(settings.database_url, "keep-me")
    service = BackupService(settings)
    recent = service.create_backup()

    old_id = "20260801T070000000000Z"
    client.put_object(Bucket="avenqo-backups", Key=f"{old_id}.json", Body=b"{}")
    client.put_object(Bucket="avenqo-backups", Key=f"{old_id}.sql", Body=b"-- old")
    prefixed_old = f"production/{old_id}.json"
    client.put_object(
        Bucket="avenqo-backups",
        Key=prefixed_old,
        Body=(
            '{"backup_id":"%s","created_at":"%s","environment":"production",'
            '"database_type":"postgresql","app_version":"0.1.0","git_revision":null,'
            '"format_version":1,"checksum_sha256":"abc","size_bytes":1}'
            % (old_id, (datetime.now(timezone.utc) - timedelta(days=45)).isoformat())
        ).encode(),
    )
    client.put_object(Bucket="avenqo-backups", Key=f"production/{old_id}.sql", Body=b"-- old prefixed")

    service._apply_retention()
    names = set(service._s3.list_names())
    assert f"{old_id}.json" in names
    assert f"{old_id}.sql" in names
    assert prefixed_old not in names
    assert f"production/{recent.backup_id}.json" in names


@mock_aws
def test_freshness_check_detects_missing_current_environment_backup(
    tmp_path, monkeypatch
) -> None:
    _make_bucket()
    settings = _settings(tmp_path, "sandbox", monkeypatch)
    _seed_sqlite(settings.database_url, "fresh")
    service = BackupService(settings)
    service.create_backup()

    from scripts.check_backup_freshness import main as freshness_main

    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "26")
    assert freshness_main() == 0

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(tmp_path / "production.db"))
    assert freshness_main() == 2
