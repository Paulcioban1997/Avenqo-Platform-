"""Test unified multi-backend storage quotas across Local and S3 without double counting."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.services.data_import_policy import (
    DataImportPolicy,
    DataImportQuotaExceeded,
)
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.storage import (
    LocalDatasetStorage,
    S3DatasetStorage,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed_company(session: Session, plan: str = "base") -> Company:
    co = Company(
        id=uuid4(),
        name="MultiStorage Test Co",
        slug=f"storage-test-{uuid4().hex[:6]}",
        email=f"storage_{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
        currency_code="CAD",
        status="active",
    )
    session.add(co)
    session.commit()
    return co


@mock_aws
def test_unified_storage_no_double_counting_across_s3_and_local(db_session):
    """Verify when S3 has local fallback, replicated files are counted exactly once."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)

    bucket_name = "avenqo-unified-storage-test"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=bucket_name)

    with TemporaryDirectory() as tmp_dir:
        artifact_root = Path(tmp_dir)
        local_storage = LocalDatasetStorage(artifact_root / "company_datasets")

        s3_storage = S3DatasetStorage(
            bucket=bucket_name,
            access_key="test_access",
            secret_key="test_secret",
            region="us-east-1",
            local_fallback=local_storage,
        )

        policy = DataImportPolicy(db_session, artifact_root=artifact_root, s3_storage=s3_storage)

        # Initially 0 bytes
        assert policy.current_storage_bytes(tenant) == 0

        # Save a 1000-byte dataset
        dataset_id = uuid4()
        raw_content = b"col1,col2\n" + (b"val1,val2\n" * 90)  # ~1000 bytes
        s3_storage.save_raw(tenant.company_id, dataset_id, 1, "test.csv", raw_content)

        # File is present in BOTH S3 and local_fallback
        s3_objects = s3_storage.list_tenant_objects(tenant.company_id)
        assert len(s3_objects) >= 1
        local_objects = local_storage.list_tenant_objects(tenant.company_id)
        assert len(local_objects) >= 1

        # Unified consumption must count it ONCE (no double counting!)
        unified_bytes = policy.current_storage_bytes(tenant)
        assert unified_bytes == len(raw_content), f"Expected {len(raw_content)} bytes without double-counting, got {unified_bytes}"

        # Delete dataset
        s3_storage.delete_dataset(tenant.company_id, dataset_id)

        # Consumption drops back to 0
        assert policy.current_storage_bytes(tenant) == 0


@mock_aws
def test_storage_quota_enforcement_with_remote_s3_objects(db_session, monkeypatch):
    """Verify S3 objects are included in cumulative quota checks and block excessive uploads."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)

    bucket_name = "avenqo-quota-s3-test"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=bucket_name)

    with TemporaryDirectory() as tmp_dir:
        artifact_root = Path(tmp_dir)
        local_storage = LocalDatasetStorage(artifact_root / "company_datasets")
        s3_storage = S3DatasetStorage(
            bucket=bucket_name,
            access_key="test_access",
            secret_key="test_secret",
            region="us-east-1",
            local_fallback=local_storage,
        )

        policy = DataImportPolicy(db_session, artifact_root=artifact_root, s3_storage=s3_storage)

        # Seed 5000 bytes directly into S3
        dataset_id = uuid4()
        s3_storage.save_raw(tenant.company_id, dataset_id, 1, "big.csv", b"x" * 5000)

        # Force a small cumulative storage limit of 6000 bytes
        monkeypatch.setattr(
            "backend.app.services.data_import_policy.data_import_limits_for",
            lambda plan: type(
                "Limits",
                (),
                {
                    "max_storage_gb": 6000 / (1024 * 1024 * 1024),
                    "max_file_mb": 10,
                    "max_storage_label": "6 KB",
                    "max_datasets": 10,
                },
            )(),
        )

        # Attempting to upload 2000 bytes (5000 existing in S3 + 2000 incoming = 7000 > 6000)
        with pytest.raises(DataImportQuotaExceeded) as exc_info:
            policy.check_storage_quota(tenant, incoming_bytes=2000)
        assert "Quota de stockage" in str(exc_info.value)
        assert "dépassé" in str(exc_info.value)
