from uuid import uuid4

from backend.app.services.artifact_storage_health import ArtifactStorageHealth
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage


def test_artifact_root_is_readable_writable_and_supports_nested_directories(tmp_path) -> None:
    root = tmp_path / "artifacts"

    status = ArtifactStorageHealth().check(root)

    assert status.status == "ok"
    assert status.readable is True
    assert status.writable is True
    assert status.nested_directories is True
    assert list(root.iterdir()) == []


def test_artifact_root_permission_failure_is_reported(monkeypatch, tmp_path) -> None:
    def deny_probe(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("tempfile.mkdtemp", deny_probe)

    status = ArtifactStorageHealth().check(tmp_path / "artifacts")

    assert status.status == "unavailable"
    assert status.readable is True
    assert status.writable is False
    assert status.nested_directories is False


def test_previous_version_remains_readable_when_new_version_is_written(tmp_path) -> None:
    storage = LocalDatasetStorage(tmp_path / "company_datasets")
    company_id = uuid4()
    other_company_id = uuid4()
    dataset_id = uuid4()
    previous = storage.save_raw(company_id, dataset_id, 1, "shopify.csv", b"version-one")

    current = storage.save_raw(company_id, dataset_id, 2, "shopify.csv", b"version-two")
    other = storage.save_raw(other_company_id, dataset_id, 1, "shopify.csv", b"other-tenant")

    assert open(previous, "rb").read() == b"version-one"
    assert open(current, "rb").read() == b"version-two"
    assert open(other, "rb").read() == b"other-tenant"
    assert str(company_id) in previous
    assert str(other_company_id) in other

    storage.delete_dataset(company_id, dataset_id)

    assert not storage.prepared_path(company_id, dataset_id, 1).parents[1].exists()
    assert open(other, "rb").read() == b"other-tenant"