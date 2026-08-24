"""Remédiation post-Phase 34 — Backup & Restore (SQLite).

Exécute un exercice de restauration RÉEL sur une base temporaire isolée
(jamais la base de développement principale) : création de fixtures
minimales -> backup -> destruction -> restauration -> vérification
d'intégrité (comptage de lignes, relations tenant, schéma).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import Settings
from backend.app.models import Base, BillingAccount, Company, CompanyStatus, User, UserRole
from backend.app.services.backup_service import (
    BackupError,
    BackupService,
    CorruptBackupError,
)


@pytest.fixture
def source_db(tmp_path: Path):
    db_path = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Acme Co", slug="acme-co", email="acme@example.com", country="CA",
            timezone="America/Toronto", industry="Retail", subscription_plan="professional",
            status=CompanyStatus.ACTIVE,
        )
        session.add(company)
        session.flush()
        user = User(
            company_id=company.id, first_name="Dana", last_name="Owner",
            email=f"owner-{uuid4()}@example.com", password_hash="hash", role=UserRole.OWNER,
        )
        billing = BillingAccount(company_id=company.id, stripe_customer_id="cus_acme")
        session.add_all([user, billing])
        session.commit()
        yield db_path, str(company.id), str(user.id)


@pytest.fixture
def backup_settings(tmp_path: Path, source_db):
    db_path, _, _ = source_db
    return Settings(
        AUTH_JWT_SECRET="e" * 32,
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        BACKUP_ROOT=str(tmp_path / "backups"),
    )


def test_create_backup_produces_metadata_and_checksum(backup_settings: Settings) -> None:
    service = BackupService(backup_settings)
    metadata = service.create_backup()

    assert metadata.database_type == "sqlite"
    assert metadata.checksum_sha256
    assert metadata.size_bytes > 0
    assert (service.root / f"{metadata.backup_id}.db").exists()
    assert (service.root / f"{metadata.backup_id}.json").exists()


def test_backup_metadata_never_contains_secrets(backup_settings: Settings) -> None:
    service = BackupService(backup_settings)
    metadata = service.create_backup()
    safe_dict = metadata.to_safe_dict()
    serialized = str(safe_dict)
    for forbidden in ("sk-", "whsec", "AUTH_JWT_SECRET", "password"):
        assert forbidden not in serialized


def test_verify_backup_rejects_corrupted_archive(backup_settings: Settings) -> None:
    service = BackupService(backup_settings)
    metadata = service.create_backup()

    corrupt_path = service.root / f"{metadata.backup_id}.db"
    with corrupt_path.open("ab") as handle:
        handle.write(b"corruption")

    with pytest.raises(CorruptBackupError):
        service.verify_backup(metadata.backup_id)


def test_restore_refuses_corrupted_archive(backup_settings: Settings, tmp_path: Path) -> None:
    service = BackupService(backup_settings)
    metadata = service.create_backup()
    corrupt_path = service.root / f"{metadata.backup_id}.db"
    with corrupt_path.open("ab") as handle:
        handle.write(b"corruption")

    target_url = f"sqlite:///{tmp_path / 'restored_corrupt.db'}"
    with pytest.raises(CorruptBackupError):
        service.restore_backup(metadata.backup_id, target_url)


def test_backup_id_path_traversal_is_rejected(backup_settings: Settings) -> None:
    service = BackupService(backup_settings)
    service.create_backup()

    for malicious_id in ("../../etc/passwd", "/etc/passwd", "..", "a/../../b"):
        with pytest.raises(BackupError):
            service.verify_backup(malicious_id)


def test_real_restore_exercise_preserves_tenant_data_integrity(
    backup_settings: Settings, source_db, tmp_path: Path
) -> None:
    _, company_id, user_id = source_db
    service = BackupService(backup_settings)
    metadata = service.create_backup()

    # "destroy/replace" : on restaure vers une base TEMPORAIRE totalement
    # distincte de la source — jamais la base de développement/production.
    restored_url = f"sqlite:///{tmp_path / 'restored_target.db'}"
    service.restore_backup(metadata.backup_id, restored_url)

    restored_engine = create_engine(restored_url)
    inspector = inspect(restored_engine)
    restored_tables = set(inspector.get_table_names())
    for expected in ("companies", "users", "billing_accounts"):
        assert expected in restored_tables

    factory = sessionmaker(bind=restored_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        companies = session.scalars(select(Company)).all()
        users = session.scalars(select(User)).all()
        billing_accounts = session.scalars(select(BillingAccount)).all()

        assert len(companies) == 1
        assert len(users) == 1
        assert len(billing_accounts) == 1

        assert str(companies[0].id) == company_id
        assert str(users[0].id) == user_id
        # Intégrité de la relation tenant (clé étrangère logique).
        assert users[0].company_id == companies[0].id
        assert billing_accounts[0].company_id == companies[0].id


def test_retention_policy_prunes_old_backups(backup_settings: Settings) -> None:
    import time

    service = BackupService(Settings(
        AUTH_JWT_SECRET=backup_settings.auth_jwt_secret,
        DATABASE_URL=backup_settings.database_url,
        BACKUP_ROOT=backup_settings.backup_root,
        BACKUP_RETENTION_DAYS=1,
    ))
    old_metadata = service.create_backup()
    old_db = service.root / f"{old_metadata.backup_id}.db"
    old_json = service.root / f"{old_metadata.backup_id}.json"
    # Simule une sauvegarde vieille de 2 jours.
    old_time = time.time() - (2 * 86400)
    import os

    os.utime(old_db, (old_time, old_time))
    os.utime(old_json, (old_time, old_time))

    service.create_backup()  # déclenche l'application de la politique de rétention

    assert not old_db.exists()
    assert not old_json.exists()
