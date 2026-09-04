from types import SimpleNamespace

from backend.app.models import DatasetStatus, JobStatus
from backend.app.routers.datasets import _pipeline_status, _training_status


def _dataset(status: DatasetStatus, *jobs: JobStatus, versions=()):
    return SimpleNamespace(
        status=status,
        training_jobs=[SimpleNamespace(status=job) for job in jobs],
        versions=list(versions),
    )


def _version(*, is_current: bool, artifact_path: str | None, row_count: int = 0):
    return SimpleNamespace(
        is_current=is_current, artifact_path=artifact_path, row_count=row_count
    )


def test_pipeline_status_tracks_ingestion_and_training_without_technical_details() -> None:
    assert _pipeline_status(_dataset(DatasetStatus.PARSING)) == "analyzing"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.PENDING)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.RUNNING)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.COMPLETED)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.FAILED)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.CANCELLED)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.MAPPING_REQUIRED)) == "attention_required"
    assert _pipeline_status(_dataset(DatasetStatus.FAILED)) == "failed"

    assert _training_status(_dataset(DatasetStatus.PARSING)) is None
    assert _training_status(_dataset(DatasetStatus.READY, JobStatus.PENDING)) == "preparing_data"
    assert _training_status(_dataset(DatasetStatus.READY, JobStatus.RUNNING)) == "training_ai"
    assert _training_status(_dataset(DatasetStatus.READY, JobStatus.COMPLETED)) == "ready"
    assert _training_status(_dataset(DatasetStatus.READY, JobStatus.FAILED)) == "training_failed"
    assert _training_status(_dataset(DatasetStatus.READY, JobStatus.CANCELLED)) == "ready"


def test_ready_dataset_with_missing_source_artifact_is_never_reported_as_ready(
    tmp_path,
) -> None:
    missing_path = str(tmp_path / "does-not-exist.csv")
    dataset = _dataset(
        DatasetStatus.READY,
        JobStatus.FAILED,
        versions=(_version(is_current=True, artifact_path=missing_path, row_count=40),),
    )
    # Even though the only training job failed (which alone would map to
    # "attention_required"), a genuinely lost raw artifact must be reported
    # as an honest processing error, not a semantic mapping issue.
    assert _pipeline_status(dataset) == "failed"


def test_ready_dataset_with_present_source_artifact_still_ready(tmp_path) -> None:
    present_path = tmp_path / "present.csv"
    present_path.write_text("a,b\n1,2\n", encoding="utf-8")
    dataset = _dataset(
        DatasetStatus.READY,
        JobStatus.COMPLETED,
        versions=(_version(is_current=True, artifact_path=str(present_path), row_count=1),),
    )
    assert _pipeline_status(dataset) == "ready"
