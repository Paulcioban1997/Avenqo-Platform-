from types import SimpleNamespace

from backend.app.models import DatasetStatus, JobStatus
from backend.app.routers.datasets import _pipeline_status


def _dataset(status: DatasetStatus, *jobs: JobStatus):
    return SimpleNamespace(
        status=status,
        training_jobs=[SimpleNamespace(status=job) for job in jobs],
    )


def test_pipeline_status_tracks_ingestion_and_training_without_technical_details() -> None:
    assert _pipeline_status(_dataset(DatasetStatus.PARSING)) == "analyzing"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.PENDING)) == "preparing_data"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.RUNNING)) == "training_ai"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.COMPLETED)) == "ready"
    assert _pipeline_status(_dataset(DatasetStatus.READY, JobStatus.FAILED)) == "attention_required"
    assert _pipeline_status(_dataset(DatasetStatus.FAILED)) == "failed"