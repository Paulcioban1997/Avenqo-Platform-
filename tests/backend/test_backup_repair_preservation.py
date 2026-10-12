"""Reproduce the deployed cron crash; preserve archives during repair.

All writes/deletions are confined to temporary SQLite and Moto S3 fixtures.
"""
import json
from datetime import datetime, timedelta, timezone
import pytest
from moto import mock_aws
from tests.backend.test_backup_s3 import s3_settings, _make_bucket
from backend.app.services.backup_service import BackupService


@mock_aws
def test_download_creates_missing_nested_parent(s3_settings, tmp_path):
    client=_make_bucket();key='sandbox/repair-fixture.json'
    body=b'{"fixture":true}'
    client.put_object(Bucket='avenqo-backups',Key=key,Body=body)
    target=tmp_path/'missing'/'sandbox'/'repair-fixture.json'
    with pytest.raises(FileNotFoundError):
        client.download_file('avenqo-backups',key,str(target))
    BackupService(s3_settings)._s3.download(key,target)
    assert target.read_bytes()==body
    assert client.get_object(Bucket='avenqo-backups',Key=key)['Body'].read()==body


@mock_aws
def test_repair_backup_preserves_expired_legacy_and_other_environment_objects(s3_settings,tmp_path,monkeypatch):
    import sqlite3
    client=_make_bucket()
    monkeypatch.setenv('ENVIRONMENT','sandbox')
    s3_settings.environment='sandbox'
    s3_settings.backup_retention_enabled=False
    s3_settings.backup_retention_days=1
    src=s3_settings.database_url.split('///',1)[1]
    with sqlite3.connect(src) as db:
        db.execute('create table fixture (value text)')
        db.execute("insert into fixture values ('preserved')")
    old=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
    objects={
        'sandbox/historical.json':json.dumps({'created_at':old}).encode(),
        'sandbox/historical.sql':b'-- existing sandbox archive',
        'production/historical.sql':b'-- existing production fixture',
        'legacy.sql':b'-- existing unprefixed fixture',
    }
    for key,body in objects.items():client.put_object(Bucket='avenqo-backups',Key=key,Body=body)
    service=BackupService(s3_settings)
    metadata=service.create_backup()
    assert metadata.environment=='sandbox'
    assert f'sandbox/{metadata.backup_id}.db' not in objects
    assert service.verify_backup(metadata.backup_id).checksum_sha256==metadata.checksum_sha256
    for key,body in objects.items():
        assert client.get_object(Bucket='avenqo-backups',Key=key)['Body'].read()==body
    target=tmp_path/'isolated-restore.db'
    service.restore_backup(metadata.backup_id,f'sqlite:///{target}')
    with sqlite3.connect(target) as db:
        assert db.execute('select value from fixture').fetchone()==('preserved',)


def test_disabled_retention_performs_no_listing_or_deletion(s3_settings,monkeypatch):
    s3_settings.backup_retention_enabled=False
    service=BackupService.__new__(BackupService)
    service._settings=s3_settings
    service._s3=object()  # no storage access is valid while retention is paused
    service._apply_retention()


@pytest.mark.parametrize('raw,expected',[('true',True),('1',True),('false',False),('0',False),(' FALSE ',False)])
def test_actual_cron_settings_load_retention_flag(monkeypatch,raw,expected):
    from scripts.backup_db import _load_backup_settings
    monkeypatch.setenv('DATABASE_URL','sqlite:///:memory:')
    monkeypatch.setenv('ENVIRONMENT','sandbox')
    monkeypatch.setenv('BACKUP_RETENTION_ENABLED',raw)
    loaded=_load_backup_settings()
    assert loaded.backup_retention_enabled is expected
    if not expected:
        service=BackupService.__new__(BackupService)
        service._settings=loaded
        service._s3=object()
        service._apply_retention()


def test_actual_cron_refuses_invalid_retention_flag(monkeypatch):
    from scripts.backup_db import _load_backup_settings
    monkeypatch.setenv('DATABASE_URL','sqlite:///:memory:')
    monkeypatch.setenv('ENVIRONMENT','sandbox')
    monkeypatch.setenv('BACKUP_RETENTION_ENABLED','invalid')
    with pytest.raises(RuntimeError,match='BACKUP_RETENTION_ENABLED'):_load_backup_settings()
