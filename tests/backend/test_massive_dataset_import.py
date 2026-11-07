"""Tests for massive dataset import quotas, S3 storage abstraction, and atomic persistence."""

import os
import io
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Company
from backend.app.services.data_import_policy import DataImportPolicy
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage, S3DatasetStorage
from payments.plans import data_import_limits_for


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_policy.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_data_import_policy_quotas(db_session):
    """Verify exact policy ceilings: Base 50MB, Pro 100MB, Enterprise 250MB."""
    global_ceiling = 250 * 1024 * 1024  # 250 MB
    policy = DataImportPolicy(db_session)

    # 1. Base tenant
    base_id = uuid4()
    base_co = Company(
        id=base_id,
        name="BaseCo",
        slug="baseco",
        email="base@co.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
        status="active",
    )
    db_session.add(base_co)
    db_session.commit()

    base_tenant = TenantContext(company_id=base_id)
    assert policy.max_upload_bytes(base_tenant, global_ceiling) == 50 * 1024 * 1024

    # 2. Professional tenant
    pro_id = uuid4()
    pro_co = Company(
        id=pro_id,
        name="ProCo",
        slug="proco",
        email="pro@co.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status="active",
    )
    db_session.add(pro_co)
    db_session.commit()

    pro_tenant = TenantContext(company_id=pro_id)
    assert policy.max_upload_bytes(pro_tenant, global_ceiling) == 100 * 1024 * 1024

    # 3. Enterprise tenant
    ent_id = uuid4()
    ent_co = Company(
        id=ent_id,
        name="EntCo",
        slug="entco",
        email="ent@co.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="enterprise",
        status="active",
    )
    db_session.add(ent_co)
    db_session.commit()

    ent_tenant = TenantContext(company_id=ent_id)
    assert policy.max_upload_bytes(ent_tenant, global_ceiling) == 250 * 1024 * 1024


def test_s3_storage_with_local_fallback(tmp_path):
    """Verify S3 storage abstraction and graceful local fallback."""
    local_root = tmp_path / "artifacts"
    local = LocalDatasetStorage(local_root)

    s3_storage = S3DatasetStorage(
        bucket="avenqo-datasets-test",
        access_key="fake_key",
        secret_key="fake_secret",
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        local_fallback=local,
    )

    company_id = uuid4()
    dataset_id = uuid4()
    version = 1
    content = b"header1,header2\nval1,val2\n"

    # Even if S3 network call fails in mock/local test, local fallback saves atomically
    saved_path = s3_storage.save_raw(company_id, dataset_id, version, "orders.csv", content)
    assert os.path.exists(saved_path)
    with open(saved_path, "rb") as f:
        assert f.read() == content
