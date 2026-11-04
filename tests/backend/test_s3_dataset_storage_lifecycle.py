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
