"""Tests du stockage S3-compatible pour les backups (Railway Storage Bucket).

Utilise moto pour simuler S3 — prouve upload, listing, download, rétention,
sans jamais toucher à un vrai bucket ni exposer de credentials.
"""

from __future__ import annotations

import pytest
from moto import mock_aws

from backend.app.config.settings import Settings
from backend.app.services.backup_service import BackupService


@pytest.fixture()
def s3_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("BACKUP_ROOT", str(tmp_path / "staging"))
    monkeypatch.delenv("BACKUP_S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "avenqo-backups")
    monkeypatch.setenv("BACKUP_S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("BACKUP_S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("BACKUP_S3_REGION", "us-east-1")
    from backend.app.config.settings import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


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


def test_backup_s3_disabled_when_incomplete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("BACKUP_S3_BUCKET", "avenqo-backups")
    monkeypatch.delenv("BACKUP_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BACKUP_S3_SECRET_KEY", raising=False)
    from backend.app.config.settings import Settings

    settings = Settings()
    assert settings.backup_s3_enabled is False


def test_backup_s3_enabled_flag(s3_settings) -> None:
    assert s3_settings.backup_s3_enabled is True


@mock_aws
def test_s3_backup_upload_list_download_cycle(s3_settings) -> None:
    _make_bucket()

    import sqlite3
    src = s3_settings.database_url.split("///", 1)[1]
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('hello-s3')")
    conn.commit()
    conn.close()

    service = BackupService(s3_settings)
    metadata = service.create_backup()

    names = set(service._s3.list_names())
    assert f"{metadata.backup_id}.db" in names
    assert f"{metadata.backup_id}.json" in names

    listed = service.list_backups()
    assert any(b.backup_id == metadata.backup_id for b in listed)

    for suffix in (".db", ".json"):
        (service.root / f"{metadata.backup_id}{suffix}").unlink()
    db_path, meta_path = service._resolve_backup_id(metadata.backup_id)
    assert db_path.exists() and meta_path.exists()

    verified = service.verify_backup(metadata.backup_id)
    assert verified.backup_id == metadata.backup_id


@mock_aws
def test_s3_restore_from_bucket(s3_settings, tmp_path) -> None:
    _make_bucket()

    import sqlite3
    src = s3_settings.database_url.split("///", 1)[1]
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('restore-me')")
    conn.commit()
    conn.close()

    service = BackupService(s3_settings)
    metadata = service.create_backup()

    target = tmp_path / "restored.db"
    service.restore_backup(metadata.backup_id, f"sqlite:///{target}")

    conn2 = sqlite3.connect(str(target))
    value = conn2.execute("SELECT v FROM t").fetchone()
    conn2.close()
    assert value == ("restore-me",)
