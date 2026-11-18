"""Tests de validation P0 : Application stricte des quotas de stockage en octets.

Vérifie :
1. Calcul réel de la consommation par tenant (octets, Mo, Go).
2. Contrôle pré-import et pendant import avec rejet explicite si dépassement de quota d'offre (Base 500 Go, Pro 2 To, Enterprise 100 To).
3. Limite de taille unitaire par fichier.
4. Récupération immédiate du quota après suppression de dataset (delete_dataset) et réimportation réussie.
5. Contrôle de la capacité physique du volume de stockage hôte (Railway / disque).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, Company, Dataset
from backend.app.models.base import CompanyStatus, DatasetStatus
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.data_import_policy import (
    DataImportFileTooLargeError,
    DataImportPolicy,
    DataImportQuotaExceeded,
    DataImportStorageUnavailableError,
)
from backend.app.services.dataset_import_service import DatasetImportService
from payments.plans import PlanCode
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def test_db(tmp_path: Path):
    db_path = tmp_path / "test_storage.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session, tmp_path
    session.close()
    engine.dispose()


def _seed_company(session: Session, plan: str = "base") -> Company:
    cid = uuid4()
    company = Company(
        id=cid,
        name=f"Entreprise Test {plan.title()}",
        slug=f"test-company-{cid.hex[:8]}",
        email=f"contact-{cid.hex[:8]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        status=CompanyStatus.ACTIVE,
        subscription_plan=plan,
    )
    session.add(company)
    session.commit()
    return company


def test_storage_quota_calculation_in_bytes(test_db):
    session, tmp_path = test_db
    company = _seed_company(session, plan="base")
    tenant = TenantContext(company_id=company.id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    policy = DataImportPolicy(session=session, artifact_root=artifacts_root)

    # Initially empty
    quota = policy.storage_quota_for_tenant(tenant)
    assert quota["plan"] == "base"
    assert quota["max_storage_gb"] == 500
    assert quota["max_storage_bytes"] == 500 * 1024 * 1024 * 1024
    assert quota["used_storage_bytes"] == 0
    assert quota["available_storage_bytes"] == 500 * 1024 * 1024 * 1024

    # Simulate stored files for this tenant
    tenant_dir = artifacts_root / str(company.id) / "datasets" / "ds1"
    tenant_dir.mkdir(parents=True)
    sample_file = tenant_dir / "data.csv"
    sample_file.write_bytes(b"A" * 1024 * 1024)  # 1 Mo

    quota_after = policy.storage_quota_for_tenant(tenant)
    assert quota_after["used_storage_bytes"] == 1024 * 1024
    assert quota_after["used_storage_mb"] == 1.0
    assert quota_after["available_storage_bytes"] == (500 * 1024 * 1024 * 1024) - (1024 * 1024)


def test_file_too_large_rejection(test_db):
    session, tmp_path = test_db
    company = _seed_company(session, plan="base")
    tenant = TenantContext(company_id=company.id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    policy = DataImportPolicy(session=session, artifact_root=artifacts_root)

    # Base plan max_file_mb is 500 * 1024 = 512 000 Mo (500 Go)
    # Check that a file exceeding max_file_mb is strictly rejected
    too_large_bytes = (500 * 1024 + 1) * 1024 * 1024
    with pytest.raises(DataImportFileTooLargeError) as exc_info:
        policy.check_storage_quota(tenant, incoming_bytes=too_large_bytes)
    assert "dépasse le plafond autorisé" in str(exc_info.value)


def test_cumulative_storage_quota_rejection(test_db):
    session, tmp_path = test_db
    company = _seed_company(session, plan="base")
    tenant = TenantContext(company_id=company.id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    policy = DataImportPolicy(session=session, artifact_root=artifacts_root)

    # Mock used storage right near the 500 GB ceiling
    max_bytes = 500 * 1024 * 1024 * 1024
    with patch.object(policy, "current_storage_bytes", return_value=max_bytes - 1000):
        # 2000 bytes will push over 500 GB
        with pytest.raises(DataImportQuotaExceeded) as exc_info:
            policy.check_storage_quota(tenant, incoming_bytes=2000)
        assert "Quota de stockage de l'offre 500 GB dépassé" in str(exc_info.value)


def test_host_disk_capacity_check(test_db):
    session, tmp_path = test_db
    company = _seed_company(session, plan="enterprise")
    tenant = TenantContext(company_id=company.id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    policy = DataImportPolicy(session=session, artifact_root=artifacts_root)

    # Mock host free disk to be 50 MB, while incoming is 100 MB
    fake_usage = MagicMock()
    fake_usage.free = 50 * 1024 * 1024
    with patch("shutil.disk_usage", return_value=fake_usage):
        with pytest.raises(DataImportStorageUnavailableError) as exc_info:
            policy.check_storage_quota(tenant, incoming_bytes=100 * 1024 * 1024)
        assert "Capacité de stockage d'infrastructure temporairement insuffisante" in str(exc_info.value)
        assert "volume Railway" in str(exc_info.value)


def test_deletion_and_reimport_quota_recalculation(test_db):
    session, tmp_path = test_db
    company = _seed_company(session, plan="base")
    tenant = TenantContext(company_id=company.id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    artifact_service = ArtifactService(artifacts_root)
    policy = DataImportPolicy(session=session, artifact_root=artifacts_root)

    import_service = DatasetImportService(
        session=session,
        artifacts=artifact_service,
        quota=policy,
        max_upload_bytes=10 * 1024 * 1024,
    )

    csv_data = b"product_id,product_name,price\nP1,Widget A,19.99\nP2,Widget B,29.99\n"
    dataset = import_service.import_csv(
        tenant=tenant,
        module_code="retail",
        filename="catalog.csv",
        content=csv_data,
    )
    assert dataset.id is not None
    stored_bytes = artifact_service.get_tenant_storage_bytes(tenant)
    assert stored_bytes == len(csv_data)

    quota_during = policy.storage_quota_for_tenant(tenant)
    assert quota_during["used_storage_bytes"] == len(csv_data)
    assert quota_during["current_datasets_count"] == 1

    # Delete dataset
    import_service.delete(tenant=tenant, dataset_id=dataset.id)

    # Storage should be immediately freed
    storage_freed = artifact_service.get_tenant_storage_bytes(tenant)
    assert storage_freed == 0
    quota_after = policy.storage_quota_for_tenant(tenant)
    assert quota_after["used_storage_bytes"] == 0
    assert quota_after["current_datasets_count"] == 0

    # Reimport succeeds cleanly
    reimported = import_service.import_csv(
        tenant=tenant,
        module_code="retail",
        filename="catalog_v2.csv",
        content=csv_data,
    )
    assert reimported.id is not None
    assert artifact_service.get_tenant_storage_bytes(tenant) == len(csv_data)
