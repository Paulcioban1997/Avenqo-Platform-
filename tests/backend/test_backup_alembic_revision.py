import json
import sqlite3
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.services.backup_service import (
    BackupService,
    extract_alembic_revision_from_dump,
)


def test_backup_metadata_records_alembic_0059(tmp_path, monkeypatch):
    db_path = tmp_path / "source.db"
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        "CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)"
    )
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES (?)",
        ("0059_migrate_role_schema_create",),
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("ENVIRONMENT", "sandbox")
    settings = Settings(
        AUTH_JWT_SECRET="e" * 32,
        ENVIRONMENT="sandbox",
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        BACKUP_ROOT=str(tmp_path / "backups"),
    )
    metadata = BackupService(settings).create_backup()
    assert metadata.alembic_revision == "0059_migrate_role_schema_create"
    payload = json.loads(
        (Path(settings.backup_root) / f"{metadata.backup_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["alembic_revision"] == "0059_migrate_role_schema_create"
    assert "password" not in json.dumps(payload)


def test_extract_alembic_revision_from_postgres_dump():
    dump = """
COPY public.alembic_version (version_num) FROM stdin;
0059_migrate_role_schema_create
\\.
"""
    assert extract_alembic_revision_from_dump(dump) == "0059_migrate_role_schema_create"
    assert (
        extract_alembic_revision_from_dump(
            "INSERT INTO public.alembic_version (version_num) VALUES ('0059_migrate_role_schema_create');"
        )
        == "0059_migrate_role_schema_create"
    )
    assert extract_alembic_revision_from_dump("SELECT 1;") is None
