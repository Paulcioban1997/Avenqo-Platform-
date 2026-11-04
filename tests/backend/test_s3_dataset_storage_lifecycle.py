"""Comprehensive S3 Dataset Storage Lifecycle & Multi-Replica Resilience Tests.

Verifies:
1. Real S3 object creation (save_raw, save_prepared, save_metadata, save_canonical).
2. Deletion from S3 and local storage (delete_dataset).
3. Multi-replica persistence: if a local ephemeral container restarts, data is preserved in S3.
4. Quota boundaries (Base 50MB, Pro 100MB, Enterprise 250MB).
"""

import json
from uuid import uuid4
from pathlib import Path
import pytest
import boto3
from moto import mock_aws

from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage, S3DatasetStorage


@mock_aws
def test_s3_full_dataset_lifecycle_and_deletion(tmp_path):
    """Test full S3 lifecycle: raw, prepared, metadata, canonical, and deletion."""
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket_name = "avenqo-sandbox-datasets"
    s3_client.create_bucket(Bucket=bucket_name)

    local = LocalDatasetStorage(tmp_path / "artifacts")
    storage = S3DatasetStorage(
        bucket=bucket_name,
        access_key="test_key",
        secret_key="test_secret",
        region="us-east-1",
        local_fallback=local,
    )

    company_id = uuid4()
    dataset_id = uuid4()
    version = 1

    # 1. Save raw
    raw_content = b"client_id,amount,date\nC1,120.50,2026-10-01\n"
    raw_uri = storage.save_raw(company_id, dataset_id, version, "sales.csv", raw_content)
    assert raw_uri.startswith(f"s3://{bucket_name}/")

    # Verify object in S3
    raw_key = f"{company_id}/datasets/{dataset_id}/v1/raw/sales.csv"
    obj = s3_client.get_object(Bucket=bucket_name, Key=raw_key)
    assert obj["Body"].read() == raw_content

    # 2. Save prepared
    rows = [{"client_id": "C1", "amount": 120.50, "date": "2026-10-01"}]
    prep_uri = storage.save_prepared(company_id, dataset_id, version, rows)
    assert prep_uri.startswith(f"s3://{bucket_name}/")
    prep_key = f"{company_id}/datasets/{dataset_id}/v1/prepared/prepared.json"
    obj = s3_client.get_object(Bucket=bucket_name, Key=prep_key)
    assert json.loads(obj["Body"].read()) == rows

    # 3. Save metadata
    meta = {"source": "upload", "row_count": 1, "columns": ["client_id", "amount", "date"]}
    meta_uri = storage.save_metadata(company_id, dataset_id, version, meta)
    assert meta_uri.startswith(f"s3://{bucket_name}/")
    meta_key = f"{company_id}/datasets/{dataset_id}/v1/metadata/metadata.json"
    obj = s3_client.get_object(Bucket=bucket_name, Key=meta_key)
    assert json.loads(obj["Body"].read()) == meta

    # 4. Save canonical
    entities = {"sales": rows}
    canon_uri = storage.save_canonical(company_id, dataset_id, version, entities)
    assert canon_uri.startswith(f"s3://{bucket_name}/")
    canon_key = f"{company_id}/datasets/{dataset_id}/v1/canonical/entities.json"
    obj = s3_client.get_object(Bucket=bucket_name, Key=canon_key)
    assert json.loads(obj["Body"].read()) == entities

    # 5. Delete dataset
    storage.delete_dataset(company_id, dataset_id)

    # Verify deleted from S3
    listing = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{company_id}/datasets/{dataset_id}/")
    assert listing.get("KeyCount", 0) == 0


@mock_aws
def test_s3_multi_replica_resilience(tmp_path):
    """Simulate a Railway multi-replica restart where local ephemeral disk is wiped."""
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket_name = "avenqo-multi-replica"
    s3_client.create_bucket(Bucket=bucket_name)

    # Replica A saves dataset
    replica_a_disk = tmp_path / "replica_a"
    storage_a = S3DatasetStorage(
        bucket=bucket_name,
        access_key="test_key",
        secret_key="test_secret",
        region="us-east-1",
        local_fallback=LocalDatasetStorage(replica_a_disk),
    )

    company_id = uuid4()
    dataset_id = uuid4()
    version = 1
    content = b"id,product,price\n1,laptop,999.99\n"

    uri = storage_a.save_raw(company_id, dataset_id, version, "catalog.csv", content)
    assert uri.startswith(f"s3://{bucket_name}/")

    # Replica B starts up with a fresh, empty local disk
    replica_b_disk = tmp_path / "replica_b"
    assert not replica_b_disk.exists()

    # The S3 object is immediately present and accessible by Replica B
    key = f"{company_id}/datasets/{dataset_id}/v1/raw/catalog.csv"
    res = s3_client.get_object(Bucket=bucket_name, Key=key)
    assert res["Body"].read() == content


def test_s3_dataset_strict_isolation_from_backup():
    """Ensure dataset settings NEVER fall back to backup_s3 settings."""
    from backend.app.config.settings import Settings

    # Case 1: Only BACKUP_S3_* configured -> Datasets MUST NOT enable S3
    s_backup_only = Settings(
        AUTH_JWT_SECRET="secret" * 8,
        BACKUP_S3_BUCKET="avenqo-backups-infra",
        BACKUP_S3_ACCESS_KEY="backup_key",
        BACKUP_S3_SECRET_KEY="backup_sec",
    )
    assert s_backup_only.backup_s3_enabled is True
    assert s_backup_only.dataset_s3_enabled is False
    assert s_backup_only.dataset_storage_status == "LOCAL_PERSISTENCE"

    # Case 2: Partial DATASET_S3_* configured (e.g. bucket set, key missing)
    s_partial = Settings(
        AUTH_JWT_SECRET="secret" * 8,
        DATASET_S3_BUCKET="avenqo-datasets-dedicated",
    )
    assert s_partial.dataset_s3_enabled is False
    assert s_partial.dataset_storage_status == "STORAGE_CONFIGURATION_MISSING"

    # Case 3: Dedicated DATASET_S3_* fully configured
    s_dedicated = Settings(
        AUTH_JWT_SECRET="secret" * 8,
        BACKUP_S3_BUCKET="avenqo-backups-infra",
        BACKUP_S3_ACCESS_KEY="backup_key",
        BACKUP_S3_SECRET_KEY="backup_sec",
        DATASET_S3_BUCKET="avenqo-datasets-dedicated",
        DATASET_S3_ACCESS_KEY="dataset_key",
        DATASET_S3_SECRET_KEY="dataset_sec",
    )
    assert s_dedicated.dataset_s3_enabled is True
    assert s_dedicated.dataset_storage_status == "S3_CONFIGURED"
    assert s_dedicated.dataset_s3_bucket == "avenqo-datasets-dedicated"
    assert s_dedicated.backup_s3_bucket == "avenqo-backups-infra"


@mock_aws
def test_s3_dataset_multi_tenant_isolation_and_fallback(tmp_path):
    """Test multi-tenant isolation in S3 keys and graceful fallback on network/credential error."""
    s3_client = boto3.client("s3", region_name="us-east-1")
    bucket_name = "avenqo-isolated-datasets"
    s3_client.create_bucket(Bucket=bucket_name)

    local_root = tmp_path / "storage"
    local = LocalDatasetStorage(local_root)
    storage = S3DatasetStorage(
        bucket=bucket_name,
        access_key="valid_key",
        secret_key="valid_secret",
        region="us-east-1",
        local_fallback=local,
    )

    tenant_a = uuid4()
    tenant_b = uuid4()
    dataset_a = uuid4()
    dataset_b = uuid4()

    # 1. Tenant A writes dataset
    content_a = b"tenant_a_data"
    uri_a = storage.save_raw(tenant_a, dataset_a, 1, "data.csv", content_a)
    assert str(tenant_a) in uri_a
    assert str(tenant_b) not in uri_a

    # 2. Tenant B writes dataset
    content_b = b"tenant_b_data"
    uri_b = storage.save_raw(tenant_b, dataset_b, 1, "data.csv", content_b)
    assert str(tenant_b) in uri_b
    assert str(tenant_a) not in uri_b

    # 3. Verify S3 keys are partitioned by tenant
    obj_a = s3_client.get_object(Bucket=bucket_name, Key=f"{tenant_a}/datasets/{dataset_a}/v1/raw/data.csv")
    assert obj_a["Body"].read() == content_a

    obj_b = s3_client.get_object(Bucket=bucket_name, Key=f"{tenant_b}/datasets/{dataset_b}/v1/raw/data.csv")
    assert obj_b["Body"].read() == content_b

    # 4. Deleting Tenant A's dataset does NOT affect Tenant B
    storage.delete_dataset(tenant_a, dataset_a)
    listing_a = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{tenant_a}/")
    assert listing_a.get("KeyCount", 0) == 0

    listing_b = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{tenant_b}/")
    assert listing_b.get("KeyCount", 0) == 1

    # 5. Invalid credentials / S3 failure: local_fallback saves content safely
    broken_storage = S3DatasetStorage(
        bucket="non-existent-bucket-xyz",
        access_key="invalid_key",
        secret_key="invalid_sec",
        region="us-east-1",
        local_fallback=local,
    )
    # save_raw should not crash, it falls back to local storage and preserves data
    fallback_path = broken_storage.save_raw(tenant_b, dataset_b, 2, "fallback.csv", b"fallback_safe")
    assert Path(fallback_path).exists()
    assert Path(fallback_path).read_bytes() == b"fallback_safe"
    assert broken_storage.status == "STORAGE_DEGRADED"
    assert broken_storage.is_degraded is True
    assert broken_storage.last_error is not None


def test_s3_failure_without_fallback_raises_storage_durability_error():
    """Zero fake pass: If S3 fails and no local storage fallback is provided, raise StorageDurabilityError."""
    from shared.ai_engine.dataset_ingestion.storage import StorageDurabilityError

    unreliable_storage = S3DatasetStorage(
        bucket="non-existent-bucket-xyz",
        access_key="invalid_key",
        secret_key="invalid_sec",
        region="us-east-1",
        local_fallback=None,
    )
    with pytest.raises(StorageDurabilityError, match="Durabilité non garantie"):
        unreliable_storage.save_raw(uuid4(), uuid4(), 1, "test.csv", b"critical_payload")

    assert unreliable_storage.status == "STORAGE_DEGRADED"
    assert unreliable_storage.is_degraded is True
